"""Executa rastros de carga de trabalho sobre a árvore AVL aumentada."""

from collections.abc import Iterator
from pathlib import Path

from tabulate import tabulate

from augmented_avl import AugmentedAVLTree
from helper_functions import PortugueseArgumentParser


def iter_trace_lines(trace_path: Path) -> Iterator[tuple[int, str, int]]:
    """Yield validated operations together with their physical line numbers.

    Args:
        trace_path: Input file containing I, D, and S operations.

    Yields:
        Physical line number, operation code, and integer key.

    Raises:
        ValueError: If a trace line is malformed.
    """
    # Lendo uma linha por vez para que traces grandes não precisem ser
    # carregados inteiros na memória.
    with trace_path.open(encoding="utf-8") as trace_file:
        for line_number, raw_line in enumerate(trace_file, 1):
            # O número físico é preservado para que erros e a tabela didática
            # apontem exatamente para a linha vista pelo usuário no arquivo.
            line = raw_line.strip()
            if not line or line.startswith("#"):
                # Comentários de metadados e linhas vazias não são operações executáveis.
                continue
            # Cada operação válida possui exatamente um código e uma chave.
            fields = line.split()
            if len(fields) != 2:
                # Rejeitar campos adicionais evita interpretar silenciosamente
                # um trace com anotações ou dados inesperados.
                raise ValueError(f"linha {line_number}: esperado '<I|D|S> <chave>', recebido {line!r}")
            # A separação ocorre somente após confirmar que existem dois campos.
            operation, raw_key = fields
            if operation not in {"I", "D", "S"}:
                # A validação centralizada impede que chamadores tratem códigos
                # desconhecidos como busca por meio de um ramo else genérico.
                raise ValueError(f"linha {line_number}: operação desconhecida {operation!r}")
            try:
                # A chave passa a ser int uma única vez antes de alcançar a árvore.
                yield line_number, operation, int(raw_key)
            except ValueError as error:
                # Preservando a exceção original como causa e acrescentando o
                # contexto da linha que falhou.
                raise ValueError(f"linha {line_number}: a chave {raw_key!r} não é um número inteiro") from error


def iter_trace(trace_path: Path) -> Iterator[tuple[str, int]]:
    """Yield validated operations from a trace file.

    Args:
        trace_path: Input file containing I, D, and S operations.

    Yields:
        Operation code and integer key for each executable line.

    Raises:
        ValueError: If a trace line is malformed.
    """
    # O benchmark não precisa do número físico. Este adaptador reutiliza toda a
    # validação do iterador detalhado sem duplicar o parser.
    for _, operation, key in iter_trace_lines(trace_path):
        yield operation, key


def iter_expected(expected_path: Path) -> Iterator[str]:
    """Yield validated search answers from an oracle file.

    Args:
        expected_path: Oracle file produced by the workload generator.

    Yields:
        Normalized ``<key> <FOUND|NOT_FOUND>`` answers.

    Raises:
        ValueError: If an oracle line is malformed.
    """
    # O oráculo também é consumido como fluxo para suportar arquivos de milhões de linhas.
    with expected_path.open(encoding="utf-8") as expected_file:
        for line_number, raw_line in enumerate(expected_file, 1):
            # split normaliza espaços entre a chave e o marcador de presença.
            fields = raw_line.split()
            if len(fields) != 2 or fields[1] not in {"FOUND", "NOT_FOUND"}:
                # O formato estrito garante que a comparação posterior seja
                # semântica, e não influenciada por texto extra.
                raise ValueError(f"linha {line_number} do oráculo: esperado '<chave> <FOUND|NOT_FOUND>'")
            try:
                # A conversão valida a chave, mesmo que a comparação use a forma textual.
                int(fields[0])
            except ValueError as error:
                raise ValueError(
                    f"linha {line_number} do oráculo: a chave {fields[0]!r} não é um número inteiro"
                ) from error
            # Juntar novamente produz uma representação canônica com um único espaço.
            yield " ".join(fields)


def run_trace(
    trace_path: Path,
    output_path: Path,
    validate_every: int = 0,
    expected_path: Path | None = None,
    show_steps: bool = False,
) -> dict[str, int]:
    """Process a trace as a stream and write answers for search operations.

    Args:
        trace_path: Input file containing I, D, and S operations.
        output_path: Destination for FOUND and NOT_FOUND answers.
        validate_every: Validate the tree after every N mutations, or zero to disable.
        expected_path: Optional oracle file used to compare every search answer.
        show_steps: Print a didactic explanation for every processed operation.

    Returns:
        Counts for insert, delete, search, and final tree size.

    Raises:
        ValueError: If validation frequency or a trace line is invalid.
    """
    # Frequência zero desativa a validação; valores negativos não possuem significado.
    if validate_every < 0:
        raise ValueError("validar-a-cada deve ser não negativo")
    # Resolver os caminhos detecta também aliases relativos para o mesmo arquivo.
    # Essa proteção acontece antes da abertura em modo escrita, que truncaria o trace.
    if trace_path.resolve() == output_path.resolve():
        raise ValueError("rastro e saída devem ser arquivos diferentes")
    # O oráculo precisa permanecer somente leitura e não pode coincidir nem com
    # a entrada nem com a saída produzida pelo candidato.
    if expected_path is not None and expected_path.resolve() in {trace_path.resolve(), output_path.resolve()}:
        raise ValueError("rastro, saída e oráculo devem ser arquivos diferentes")

    # Uma execução de trace sempre começa com uma árvore vazia, como pressupõe o gerador.
    tree = AugmentedAVLTree()
    # As contagens efetivas são separadas porque a mistura produzida pode diferir
    # da mistura nominal solicitada ao gerador.
    counts = {"I": 0, "D": 0, "S": 0}
    # mutations controla a periodicidade sem contar buscas, que não alteram invariantes.
    mutations = 0
    # Correspondências e divergências são mantidas separadamente para produzir
    # um resumo verificável e um código de saída adequado.
    oracle_matches = 0
    oracle_mismatches = 0
    # Criar o iterador somente quando há oráculo mantém esse recurso opcional.
    expected_answers = iter(iter_expected(expected_path)) if expected_path is not None else None
    # As linhas da tabela são acumuladas apenas no modo didático. Isso permite
    # que tabulate calcule larguras comuns; o modo experimental continua streaming.
    step_rows: list[list[str]] = []

    # Abrir com "w" garante que candidate contenha somente respostas desta execução.
    with output_path.open("w", encoding="utf-8") as output_file:
        for line_number, operation, key in iter_trace_lines(trace_path):
            if operation == "I":
                # O texto da ação distingue inserção real de duplicata ignorada.
                action = "inserida" if tree.insert(key) else "já existente"
            elif operation == "D":
                # A remoção ausente é válida no trace e aparece explicitamente na explicação.
                action = "removida" if tree.delete(key) else "não encontrada"
            else:
                # O parser já restringiu os códigos, então o ramo restante é uma busca.
                result = "FOUND" if tree.search(key) else "NOT_FOUND"
                # O candidato deve reproduzir exatamente o formato chave + resultado.
                obtained = f"{key} {result}"
                # Somente buscas geram linhas no arquivo avaliado pelo oráculo.
                print(obtained, file=output_file)

                # Consumindo uma linha do oráculo apenas para cada busca. As
                # inserções e remoções não produzem linhas no arquivo expected.
                expected = None
                if expected_answers is not None:
                    try:
                        # Cada busca consome exatamente uma resposta, preservando a ordem temporal.
                        expected = next(expected_answers)
                    except StopIteration as error:
                        # Um oráculo curto não pode ser aceito como comparação parcial.
                        raise ValueError(
                            f"o oráculo terminou antes da busca na linha {line_number} do rastro"
                        ) from error
                    if obtained == expected:
                        oracle_matches += 1
                    else:
                        oracle_mismatches += 1

                if show_steps:
                    # Sem oráculo não existe veredito. Com oráculo, cada linha recebe
                    # OK ou DIVERGÊNCIA sem interromper a inspeção das demais operações.
                    comparison = "-" if expected is None else "OK" if obtained == expected else "DIVERGÊNCIA"
                    # Todas as células são strings para impedir alinhamentos numéricos
                    # inesperados e manter a apresentação estável no terminal.
                    step_rows.append(
                        [str(line_number), f"S {key}", "busca", obtained, expected or "não informado", comparison]
                    )
            # A contagem acontece depois da operação ser executada com sucesso.
            counts[operation] += 1
            if operation in {"I", "D"}:
                if show_steps:
                    # Inserções e remoções não possuem saída no oráculo; os hífens
                    # deixam essa ausência explícita sem deslocar as colunas.
                    step_rows.append([str(line_number), f"{operation} {key}", action, "-", "sem saída", "-"])
                mutations += 1
                if validate_every and mutations % validate_every == 0:
                    # A validação periódica encontra cedo a primeira mutação que
                    # corrompa ordenação, balanceamento, parents ou metadados.
                    tree.assert_valid()

    # Verificando também se sobraram respostas. Isso fecha a lacuna do
    # verificador fornecido, que compara arquivos com zip e pode ignorar caudas.
    if expected_answers is not None:
        try:
            # Consumir mais uma linha é suficiente para provar que o oráculo é longo.
            extra_answer = next(expected_answers)
        except StopIteration:
            # O esgotamento simultâneo confirma a mesma quantidade de respostas.
            pass
        else:
            raise ValueError(f"o oráculo possui resposta excedente após o rastro: {extra_answer!r}")

    if validate_every:
        # A checagem final cobre mutações restantes quando a quantidade não é
        # múltipla exata de validate_every.
        tree.assert_valid()
    if show_steps:
        # fancy_grid usa as larguras calculadas sobre todas as linhas e torna
        # operações, valores e vereditos visualmente comparáveis.
        print(
            tabulate(
                step_rows,
                headers=["Linha", "Operação", "Ação", "Obtido", "Esperado", "Conferência"],
                tablefmt="fancy_grid",
                disable_numparse=True,
            )
        )
    # O tamanho final vem do metadado size da raiz depois de todas as mutações.
    counts["final_size"] = len(tree)
    # Acrescentando os resultados do oráculo ao mesmo resumo retornado ao CLI.
    counts["oracle_matches"] = oracle_matches
    counts["oracle_mismatches"] = oracle_mismatches
    return counts


def main(argv: list[str] | None = None) -> int:
    """Parse command-line arguments and execute one trace.

    Args:
        argv: Optional argument list for tests and embedding.

    Returns:
        Process exit code.
    """
    parser = PortugueseArgumentParser(description=__doc__)
    parser.add_argument("trace", metavar="RASTRO", type=Path, help="arquivo .trace de entrada")
    parser.add_argument(
        "--saida", dest="output", metavar="ARQUIVO", type=Path, required=True, help="caminho da saída do candidato"
    )
    parser.add_argument(
        "--esperado",
        dest="expected",
        metavar="ARQUIVO",
        type=Path,
        help="arquivo .expected opcional usado como oráculo",
    )
    parser.add_argument(
        "--mostrar-passos",
        dest="show_steps",
        action="store_true",
        help="explica cada operação e sua comparação",
    )
    parser.add_argument(
        "--validar-a-cada",
        dest="validate_every",
        metavar="N",
        type=int,
        default=0,
        help="valida invariantes após cada N mutações (0 desativa)",
    )
    args = parser.parse_args(argv)
    # A tabela inicial torna explícitos os três artefatos antes de qualquer
    # processamento e ajuda a detectar rapidamente caminhos trocados.
    print(
        tabulate(
            [
                ["Rastro", args.trace.resolve()],
                ["Candidato", args.output.resolve()],
                ["Oráculo", args.expected.resolve() if args.expected else "não informado"],
            ],
            headers=["Arquivo", "Caminho"],
            tablefmt="fancy_grid",
            disable_numparse=True,
        )
    )
    try:
        # A função principal converte falhas esperadas de arquivo ou conteúdo
        # em erros de linha de comando, sem expor traceback ao usuário final.
        counts = run_trace(args.trace, args.output, args.validate_every, args.expected, args.show_steps)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    # Qualquer divergência torna a execução incorreta, ainda que o trace inteiro
    # tenha sido processado e o candidate tenha sido produzido.
    status = "[sucesso]" if counts["oracle_mismatches"] == 0 else "[erro]"
    print(
        f"{status} inserções={counts['I']} remoções={counts['D']} "
        f"buscas={counts['S']} tamanho_final={counts['final_size']}"
    )
    if args.expected is not None:
        # O denominador usa o número de buscas, que deve coincidir com as linhas do oráculo.
        print(f"[oráculo] {counts['oracle_matches']}/{counts['S']} respostas de busca conferem")
    # O código não zero permite que scripts e sistemas de CI detectem a divergência.
    return 1 if counts["oracle_mismatches"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
