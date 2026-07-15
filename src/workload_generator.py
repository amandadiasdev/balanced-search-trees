#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
workload_generator.py -- Gerador de cargas de trabalho
(inserção/remoção/busca) e oráculo de referência para avaliação de estruturas
de dados em larga escala.

Subcomandos:
  gerar      -> a partir de um conjunto de chaves reais (SOSD ou texto),
                produz um arquivo de rastro (.trace) e o gabarito (.expected).
  verificar  -> compara a saída da estrutura do grupo (.out) com o gabarito.

Formato do rastro (uma operação por linha):
    I <chave>      inserção
    D <chave>      remoção
    S <chave>      busca

Formato do gabarito (.expected), apenas para operações S, na ordem:
    <chave> <FOUND|NOT_FOUND>

A correção das operações I e D é verificada de forma transitiva. O resultado
esperado de cada busca depende de todas as inserções e remoções anteriores,
de modo que uma implementação incorreta de I ou D produz divergência em S.

O padrão de acesso segue uma distribuição Zipfiana no estilo YCSB. Poucas
chaves concentram a maior parte das buscas e remoções, estressando o
rebalanceamento e a localidade de cache de formas diferentes de um acesso
uniforme.
"""

import argparse
import struct
import sys
import random
import numpy as np

from helper_functions import PortugueseArgumentParser


# Implementando o gerador Zipfiano descrito por Gray et al. e adotado pelo
# YCSB. A distribuição concentra muitos acessos nos ranks mais baixos.
class Zipfian:
    def __init__(self, n, theta, seed):
        # A fórmula exige pelo menos um rank. Normalizar aqui evita que todos os
        # chamadores precisem tratar conjuntos temporariamente vazios.
        if n < 1:
            n = 1
        # n define quantos ranks distintos a distribuição pode devolver.
        self.n = n
        # theta controla a assimetria: valores próximos de um intensificam a
        # preferência pelos itens mais quentes.
        self.theta = theta
        # Um gerador local preserva reprodutibilidade sem alterar o estado
        # pseudoaleatório global usado por outras partes do programa.
        self.rng = random.Random(seed)
        # zeta_n normaliza a distribuição para o universo completo de ranks.
        self.zeta_n = self._zeta(n, theta)
        # zeta2 é a constante usada para tratar os dois primeiros ranks quentes.
        self.zeta2 = self._zeta(2, theta)
        # alpha transforma a amostra uniforme conforme o expoente Zipfiano.
        self.alpha = 1.0 / (1.0 - theta)
        # eta ajusta a aproximação para o tamanho concreto do universo. Esses
        # termos são pré-calculados porque serão reutilizados em toda amostra.
        self.eta = (1.0 - (2.0 / n) ** (1.0 - theta)) / (1.0 - self.zeta2 / self.zeta_n)

    @staticmethod
    def _zeta(n, theta):
        # Soma de 1/i^theta para i = 1..n, calculada em blocos para limitar memoria.
        # total acumula os blocos sem materializar um vetor com n posições.
        total = 0.0
        # Um milhão equilibra chamadas NumPy vetorizadas e uso temporário de memória.
        chunk = 1_000_000
        # Os ranks matemáticos começam em um, pois zero causaria divisão por zero.
        i = 1
        while i <= n:
            # j fecha o bloco atual sem ultrapassar o último rank disponível.
            j = min(i + chunk - 1, n)
            # arange cria somente os índices deste bloco em precisão suficiente
            # para a soma normalizadora.
            idx = np.arange(i, j + 1, dtype=np.float64)
            # A operação vetorizada calcula e soma as parcelas do bloco.
            total += float(np.sum(1.0 / np.power(idx, theta)))
            # O próximo bloco começa imediatamente após o índice já processado.
            i = j + 1
        return total

    def next_rank(self):
        """Retorna um rank em [0, n); ranks baixos sao os mais 'quentes'."""
        # A amostra uniforme é transformada pela inversa aproximada da CDF Zipfiana.
        u = self.rng.random()
        # Multiplicar pela normalização permite identificar diretamente as
        # regiões reservadas aos dois ranks de maior probabilidade.
        uz = u * self.zeta_n
        if uz < 1.0:
            # A primeira massa acumulada corresponde ao rank mais quente.
            return 0
        if uz < 1.0 + (0.5 ** self.theta):
            # A segunda massa acumulada corresponde ao rank um.
            return 1
        # Os demais ranks seguem a transformação contínua parametrizada por eta e alpha.
        return int(self.n * ((self.eta * u - self.eta + 1.0) ** self.alpha))


# Mantendo o conjunto de chaves vivas com duas representações sincronizadas.
# A lista permite amostragem por posição em O(1), enquanto o mapa permite
# presença, inserção e localização para remoção também em O(1) esperado.
class LiveSet:
    def __init__(self):
        self.arr = []          # chaves atualmente inseridas
        self.pos = {}          # chave -> indice em arr

    def __len__(self):
        return len(self.arr)

    def contains(self, key):
        return key in self.pos

    def add(self, key):
        # O mapa é a fonte de verdade para presença e impede duplicatas na lista.
        if key in self.pos:
            return False
        # A nova chave ocupará a posição posterior ao último elemento atual.
        self.pos[key] = len(self.arr)
        # A lista e o mapa são atualizados em sequência para preservar o mesmo índice.
        self.arr.append(key)
        return True

    def remove(self, key):
        # get diferencia chave ausente sem realizar duas consultas ao dicionário.
        i = self.pos.get(key)
        if i is None:
            return False
        # O último elemento será movido para o espaço deixado pela remoção. Isso
        # evita deslocar todos os elementos posteriores como list.pop(i) faria.
        last = self.arr[-1]
        # Sobrescrevendo a posição removida com a chave que estava no fim.
        self.arr[i] = last
        # Atualizando o índice da chave movida antes de encurtar a lista.
        self.pos[last] = i
        # A última posição agora é redundante e pode ser descartada em O(1).
        self.arr.pop()
        # Finalmente, removendo do mapa a chave que deixou o conjunto vivo.
        del self.pos[key]
        return True

    def at_rank(self, rank):
        # Zipfiano "embaralhado" sobre o conjunto vivo: a posicao quente varia
        # conforme insercoes/remocoes, decorrelacionando rank de valor de chave.
        # O módulo protege contra um rank maior que o tamanho vivo atual, que
        # pode ter diminuído desde a criação do gerador Zipfiano.
        return self.arr[rank % len(self.arr)]


# Carregando chaves reais em formato SOSD binário ou em formato textual.
def load_keys(path, fmt, key_bytes, max_load=0):
    # No modo automático, extensões textuais conhecidas escolhem texto. Os
    # demais arquivos seguem o layout binário usado pelos datasets SOSD.
    if fmt == "sosd" or (fmt == "auto" and not path.endswith((".txt", ".csv"))):
        # O tamanho da chave precisa coincidir com o dataset para interpretar os bytes.
        dtype = np.uint32 if key_bytes == 4 else np.uint64
        with open(path, "rb") as f:
            # O cabeçalho SOSD guarda a quantidade de chaves em uint64 little-endian.
            n = struct.unpack("<Q", f.read(8))[0]
            if max_load:
                # Limitando antes de np.fromfile para não alocar as chaves excedentes.
                n = min(n, max_load)            # le apenas as primeiras n chaves
            # A leitura começa depois do cabeçalho e consome exatamente n valores.
            arr = np.fromfile(f, dtype=dtype, count=n)
        # Normalizar para uint64 produz o mesmo tipo interno para datasets de 32 e 64 bits.
        return arr.astype(np.uint64)
    # texto: um inteiro por linha
    # None instrui loadtxt a ler tudo; um inteiro positivo impõe o mesmo limite
    # disponibilizado para o formato binário.
    rows = max_load if max_load else None
    return np.loadtxt(path, dtype=np.uint64, max_rows=rows)


def synthetic_keys(n, seed):
    # default_rng oferece um fluxo reproduzível independente do módulo random.
    rng = np.random.default_rng(seed)
    # chaves densas com lacunas irregulares, lembrando dados reais
    # Lacunas sempre positivas garantem chaves crescentes e distintas antes de
    # qualquer embaralhamento realizado pelo gerador de carga.
    gaps = rng.integers(1, 40, size=n, dtype=np.uint64)
    # A soma cumulativa transforma cada lacuna no valor absoluto da próxima chave.
    return np.cumsum(gaps, dtype=np.uint64)


# Gerando o trace e o gabarito a partir da mesma sequência de decisões. O
# LiveSet atua como oráculo de estado e registra quais chaves estão presentes.
def generate(args):
    if args.synthetic:
        # O modo sintético permite smoke tests sem depender de um dataset externo.
        keys = synthetic_keys(args.synthetic, args.seed)
    else:
        # O modo experimental carrega as chaves do arquivo indicado pelo grupo.
        keys = load_keys(args.keys, args.format, args.key_bytes, args.max_load)

    # Eliminar duplicatas é obrigatório porque a estrutura avaliada representa
    # um conjunto e cada chave deve possuir uma única identidade no universo.
    keys = np.unique(keys)                      # garante chaves distintas
    # Este gerador controla escolha do universo, operações e alvos de forma reproduzível.
    rng = random.Random(args.seed)

    # U limita o universo após a deduplicação. Zero significa usar todas as chaves.
    U = min(args.universe, len(keys)) if args.universe else len(keys)
    # Embaralhar índices seleciona uma amostra sem copiar previamente o vetor de chaves.
    idx = list(range(len(keys)))
    rng.shuffle(idx)
    # Somente as U posições sorteadas participarão desta carga.
    chosen = keys[idx[:U]]

    # Reserva uma fracao de chaves que NUNCA sao inseridas, para testar buscas
    # com resultado NOT_FOUND de forma garantida.
    # R é calculado sobre o universo efetivo, não sobre o arquivo completo.
    R = int(U * args.reserve)
    # Chaves reservadas alimentam misses e remoções ausentes, mas nunca inserções.
    reserved = chosen[:R]
    # As chaves restantes formam a fonte finita de inserções válidas.
    insertable = chosen[R:]

    # Ordem de insercao
    if args.insert_order == "sorted":
        # A ordem crescente cria o caso patológico de uma BST sem balanceamento.
        insert_order = np.sort(insertable).tolist()     # caso patologico p/ BST
    elif args.insert_order == "popularity":
        # A ordem já amostrada preserva a associação entre posição e popularidade.
        insert_order = insertable.tolist()              # ordem ja embaralhada
    else:
        # shuffle produz uma permutação reproduzível independente da ordem das chaves.
        order = list(insertable)
        rng.shuffle(order)
        insert_order = order

    # live representa exatamente o estado que a árvore candidata deveria possuir.
    live = LiveSet()
    # Chaves removidas permanecem disponíveis como alvos que verificam delete transitivamente.
    deleted = []          # chaves removidas (nunca reinseridas) -> testam D via S
    # Os geradores usam sementes distintas para não correlacionar hits e misses.
    zipf_live = Zipfian(max(len(insertable), 1), args.theta, args.seed + 1)
    zipf_miss = Zipfian(max(len(reserved), 1), args.theta, args.seed + 2)

    # Convertendo a mistura textual em probabilidades acumuláveis.
    p_ins, p_del, p_srch = _mix(args.mix)
    # next_insert garante que cada chave inserível seja usada no máximo uma vez.
    next_insert = 0
    # Os contadores registram a mistura efetivamente emitida e a taxa real de acertos.
    n_ins = n_del = n_srch = n_hit = n_miss = 0

    # Trace e expected são escritos juntos para que cada busca emitida receba
    # imediatamente a resposta correspondente ao estado atual de live.
    with open(args.out + ".trace", "w") as ft, open(args.out + ".expected", "w") as fe:
        # O cabeçalho guarda os parâmetros necessários para reproduzir e auditar a carga.
        ft.write(f"# universe={U} reserve={R} mix={args.mix} theta={args.theta} "
                 f"seed={args.seed} insert_order={args.insert_order} ops={args.ops}\n")
        for _ in range(args.ops):
            # Uma amostra uniforme escolhe a faixa acumulada de I, D ou S.
            r = rng.random()

            # Forca insercoes enquanto o conjunto vivo estiver vazio.
            if len(live) == 0:
                # Não é possível produzir hit nem remover chave presente com live vazio.
                op = "I"
            elif r < p_ins and next_insert < len(insert_order):
                # A primeira faixa da distribuição corresponde às inserções.
                op = "I"
            elif r < p_ins + p_del:
                # A segunda faixa soma inserção e remoção para formar o limite acumulado.
                op = "D"
            else:
                # Toda probabilidade restante corresponde a buscas.
                op = "S"

            if op == "I":
                if next_insert >= len(insert_order):
                    # Após esgotar chaves únicas, emitir outra inserção violaria o
                    # contrato de não reinserção adotado pelo gerador.
                    op = "S"                     # esgotou chaves inseriveis
                else:
                    # Consumindo a próxima chave segundo a ordem escolhida pelo experimento.
                    key = insert_order[next_insert]
                    next_insert += 1
                    # Atualizando o oráculo antes que buscas futuras consultem a chave.
                    live.add(int(key))
                    # O trace recebe somente a operação; inserções não geram expected.
                    ft.write(f"I {int(key)}\n")
                    n_ins += 1
                    continue

            if op == "D":
                if rng.random() < args.absent and R > 0:
                    # Uma remoção ausente usa chave reservada para ter ausência garantida.
                    key = int(reserved[zipf_miss.next_rank() % R])    # remover ausente
                else:
                    # A remoção normal escolhe uma chave atualmente viva sob Zipf.
                    key = int(live.at_rank(zipf_live.next_rank()))
                    # O oráculo remove antes de qualquer busca subsequente.
                    live.remove(key)
                    # Manter a chave em deleted permite verificar a remoção com um miss futuro.
                    deleted.append(key)          # passa a ser alvo de buscas-miss
                # Remoções, presentes ou ausentes, são registradas somente no trace.
                ft.write(f"D {key}\n")
                n_del += 1
                continue

            # op == "S"
            # Um hit só pode ser solicitado quando existe ao menos uma chave viva.
            want_hit = (rng.random() < args.hit) and len(live) > 0
            if want_hit:
                # A distribuição Zipfiana concentra buscas em posições quentes de live.
                key = int(live.at_rank(zipf_live.next_rank()))
                # A presença é conhecida pelo próprio LiveSet usado para escolher a chave.
                result = "FOUND"
                n_hit += 1
            else:
                # Busca-miss: ora chave reservada (nunca inserida), ora chave
                # ja REMOVIDA. Esta ultima e o que testa a corretude de D via S.
                if deleted and rng.random() < args.deleted_miss:
                    # Uma chave removida detecta candidatos que falharam ao executar delete.
                    key = int(deleted[rng.randrange(len(deleted))])
                elif R > 0:
                    # A chave reservada detecta falsos positivos sem depender de remoções prévias.
                    key = int(reserved[zipf_miss.next_rank() % R])
                elif deleted:
                    # Sem reserva, uma remoção anterior ainda fornece um miss garantido.
                    key = int(deleted[rng.randrange(len(deleted))])
                else:
                    # Se não há nenhuma fonte de miss, a busca precisa se tornar
                    # um hit para continuar produzindo uma operação válida.
                    key = int(live.at_rank(zipf_live.next_rank()))
                    result = "FOUND"
                    n_hit += 1
                    # Escrevendo trace e resposta juntos antes de encerrar esta iteração.
                    ft.write(f"S {key}\n")
                    fe.write(f"{key} {result}\n")
                    n_srch += 1
                    continue
                # Todos os ramos anteriores selecionaram uma chave comprovadamente ausente.
                result = "NOT_FOUND"
                n_miss += 1
            # Cada busca produz uma linha no trace e exatamente uma linha no gabarito.
            ft.write(f"S {key}\n")
            fe.write(f"{key} {result}\n")
            n_srch += 1

    # O resumo vai para stderr para não misturar informações humanas com dados
    # que possam ser redirecionados a partir de stdout.
    sys.stderr.write(
        f"[sucesso] {args.out}.trace e {args.out}.expected gerados\n"
        f"          inserções={n_ins}  remoções={n_del}  buscas={n_srch} "
        f"(encontradas={n_hit}, não encontradas={n_miss})\n"
        f"          chaves ativas ao final={len(live)}  universo={U}  reservadas={R}\n"
    )


def _mix(spec):
    # A interface textual I:D:S é decomposta na ordem esperada pelo seletor de operações.
    parts = [float(x) for x in spec.split(":")]
    # A soma transforma pesos arbitrários, como 45:25:30, em probabilidades.
    s = sum(parts)
    # Dividir cada parcela pela soma preserva a proporção e totaliza um.
    return parts[0] / s, parts[1] / s, parts[2] / s


# Comparando as respostas do candidato com o gabarito na ordem das buscas.
def verify(args):
    # mism contabiliza divergências; total contabiliza pares efetivamente comparados.
    mism = 0
    total = 0
    # Somente a primeira divergência é guardada para produzir um diagnóstico conciso.
    first = None
    # Os dois arquivos são percorridos em paralelo sem serem carregados na memória.
    with open(args.expected) as fe, open(args.candidate) as fc:
        for ln, (e, c) in enumerate(zip(fe, fc), 1):
            total += 1
            # strip neutraliza apenas espaços periféricos e quebras de linha.
            if e.strip() != c.strip():
                mism += 1
                if first is None:
                    # Preservando número, esperado e obtido para a mensagem final.
                    first = (ln, e.strip(), c.strip())
    if mism == 0:
        # Zero divergências nos pares comparados representa sucesso segundo este verificador.
        print(f"[SUCESSO] {total} buscas conferidas, nenhuma divergência.")
        return 0
    # O resumo informa a extensão do erro antes de detalhar o primeiro exemplo.
    print(f"[FALHA] {mism}/{total} divergências.")
    if first:
        print(f"       1ª divergência na linha {first[0]}: "
              f"esperado='{first[1]}'  obtido='{first[2]}'")
    # Código um permite detectar a falha em scripts de automação.
    return 1


def main():
    # RawDescriptionHelpFormatter preserva as quebras do texto explicativo do módulo.
    p = PortugueseArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    # O subcomando é obrigatório para separar geração e verificação em contratos claros.
    sub = p.add_subparsers(dest="cmd", required=True)

    # Configurando os argumentos exclusivos do fluxo de geração.
    g = sub.add_parser("gerar", help="gera rastro e gabarito")
    # Exatamente uma fonte de chaves deve ser escolhida: arquivo ou geração sintética.
    src = g.add_mutually_exclusive_group(required=True)
    src.add_argument(
        "--chaves", dest="keys", metavar="ARQUIVO", help="arquivo de chaves (SOSD binário ou texto)"
    )
    src.add_argument(
        "--sintetico", dest="synthetic", metavar="N", type=int, help="gera N chaves sintéticas para teste"
    )
    g.add_argument(
        "--formato",
        dest="format",
        choices=["automatico", "sosd", "texto"],
        default="automatico",
        help="formato do arquivo de chaves",
    )
    g.add_argument("--bytes-chave", dest="key_bytes", metavar="N", type=int, choices=[4, 8], default=8)
    g.add_argument(
        "--carga-maxima",
        dest="max_load",
        metavar="N",
        type=int,
        default=0,
        help="lê no máximo N chaves do arquivo (0 lê todas)",
    )
    g.add_argument("--saida", dest="out", metavar="PREFIXO", required=True, help="prefixo dos arquivos de saída")
    g.add_argument("--operacoes", dest="ops", metavar="N", type=int, default=1_000_000, help="número de operações")
    g.add_argument(
        "--universo",
        dest="universe",
        metavar="N",
        type=int,
        default=0,
        help="número de chaves distintas usadas (0 usa todas)",
    )
    g.add_argument(
        "--mistura", dest="mix", metavar="I:D:S", default="50:20:30", help="proporção I:D:S, por exemplo 50:20:30"
    )
    g.add_argument("--theta", metavar="VALOR", type=float, default=0.99,
                   help="parâmetro Zipfiano (0 é uniforme; 0.99 é o padrão YCSB)")
    g.add_argument(
        "--reserva",
        dest="reserve",
        metavar="FRAÇÃO",
        type=float,
        default=0.10,
        help="fração de chaves nunca inseridas",
    )
    g.add_argument(
        "--acertos", dest="hit", metavar="FRAÇÃO", type=float, default=0.7, help="fração alvo de buscas encontradas"
    )
    g.add_argument(
        "--remocoes-ausentes",
        dest="absent",
        metavar="FRAÇÃO",
        type=float,
        default=0.05,
        help="fração de remoções de chaves ausentes",
    )
    g.add_argument(
        "--buscas-em-removidas",
        dest="deleted_miss",
        metavar="FRAÇÃO",
        type=float,
        default=0.5,
        help="fração das buscas não encontradas que usam chaves removidas",
    )
    g.add_argument(
        "--ordem-insercao",
        dest="insert_order",
        choices=["embaralhada", "ordenada", "popularidade"],
        default="embaralhada",
        help="ordem em que as chaves serão inseridas",
    )
    g.add_argument("--semente", dest="seed", metavar="N", type=int, default=42)
    # Associando o subcomando diretamente à função que o implementa.
    g.set_defaults(func=generate)

    # Configurando os dois arquivos necessários ao fluxo de verificação.
    v = sub.add_parser("verificar", help="compara a saída do candidato com o gabarito")
    v.add_argument(
        "--esperado", dest="expected", metavar="ARQUIVO", required=True, help="arquivo .expected do oráculo"
    )
    v.add_argument(
        "--candidato", dest="candidate", metavar="ARQUIVO", required=True, help="arquivo produzido pela árvore"
    )
    v.set_defaults(func=verify)

    # parse_args devolve um namespace que inclui func definido pelo subcomando.
    args = p.parse_args()
    if args.cmd == "gerar":
        # Convertendo os valores públicos em português para os códigos internos
        # preservados nos metadados do rastro e nas decisões do gerador.
        args.format = {"automatico": "auto", "sosd": "sosd", "texto": "text"}[args.format]
        args.insert_order = {
            "embaralhada": "shuffle",
            "ordenada": "sorted",
            "popularidade": "popularity",
        }[args.insert_order]
    # Ambas as funções podem retornar None em sucesso; rc or 0 normaliza esse caso.
    rc = args.func(args)
    sys.exit(rc or 0)


if __name__ == "__main__":
    main()
