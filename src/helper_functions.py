"""Small didactic replacements and shared helpers used by the command-line tools."""

import argparse
import sys
from collections.abc import Sequence
from typing import Any, NoReturn

# Este módulo recebe somente mecanismos gerais, sem conhecer árvore, trace,
# benchmark ou esquemas de resultados. Essa restrição evita transformá-lo em
# um depósito de funções que possuem pouco em comum além de serem reutilizáveis.


class PortugueseArgumentParser(argparse.ArgumentParser):
    """Display argparse help and errors in Brazilian Portuguese.

    The standard parser delegates automatic labels and diagnostics to the
    process locale, which is not guaranteed to be configured in Portuguese.
    This specialization keeps the three project CLIs consistent regardless of
    the operating-system locale.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Create a parser with Portuguese section titles and help option.

        Args:
            *args: Positional arguments accepted by ``ArgumentParser``.
            **kwargs: Keyword arguments accepted by ``ArgumentParser``.
        """
        # Desativando a ajuda automática porque ela criaria a opção inglesa
        # --help. A forma curta -h é preservada por ser uma convenção universal.
        kwargs["add_help"] = False
        super().__init__(*args, **kwargs)
        self._positionals.title = "argumentos posicionais"
        self._optionals.title = "opções"
        self.add_argument("-h", "--ajuda", action="help", help="exibe esta ajuda e encerra")

    def format_usage(self) -> str:
        """Return the usage line with a Portuguese prefix.

        Returns:
            Formatted usage text.
        """
        return super().format_usage().replace("usage:", "uso:", 1)

    def format_help(self) -> str:
        """Return the complete help text with a Portuguese usage prefix.

        Returns:
            Formatted help text.
        """
        return super().format_help().replace("usage:", "uso:", 1)

    def error(self, message: str) -> NoReturn:
        """Print a localized command-line error and terminate.

        Args:
            message: Diagnostic produced by argparse or by the application.

        Raises:
            SystemExit: Always raised with exit status 2.
        """
        # Traduzindo as construções automáticas mais comuns do argparse. Erros
        # produzidos diretamente pelo projeto já chegam escritos em PT-BR.
        translations = {
            "the following arguments are required:": "os seguintes argumentos são obrigatórios:",
            "one of the arguments": "um dos argumentos",
            "is required": "é obrigatório",
            "unrecognized arguments:": "argumentos não reconhecidos:",
            "invalid choice:": "escolha inválida:",
            "invalid int value:": "valor inteiro inválido:",
            "invalid float value:": "valor decimal inválido:",
            "choose from": "escolha entre",
            "expected one argument": "esperava um argumento",
            "not allowed with argument": "não é permitido com o argumento",
            "argument ": "argumento ",
        }
        for source, translated in translations.items():
            message = message.replace(source, translated)
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: erro: {message}\n")


def bisect_left(values: Sequence[int], target: int) -> int:
    """Return the first position where a target can be inserted.

    The sequence must already be sorted in ascending order. If the target is
    repeated, the returned position precedes every occurrence.

    Args:
        values: Sorted integer sequence.
        target: Value whose insertion position is required.

    Returns:
        Index of the left insertion boundary.
    """
    # lower é uma posição que já pode ser descartada como resposta enquanto
    # upper delimita a primeira posição ainda não examinada.
    lower = 0
    # Usar len(values), em vez do último índice, permite devolver uma posição
    # imediatamente após o fim quando target é maior que todos os elementos.
    upper = len(values)

    # Mantendo o intervalo de busca no formato [lower, upper). Isso permite
    # representar também a posição logo depois do último elemento.
    while lower < upper:
        # O ponto médio divide ao meio o intervalo que ainda pode conter a
        # primeira posição válida, garantindo complexidade logarítmica.
        middle = (lower + upper) // 2
        if values[middle] < target:
            # Se o valor central é menor, nem middle nem qualquer posição à
            # esquerda pode receber target sem quebrar a ordenação.
            lower = middle + 1
        else:
            # Igualdade também move upper para a esquerda. Essa é a decisão que
            # faz a função encontrar a primeira ocorrência entre duplicatas.
            upper = middle
    # Quando os limites se encontram, todo índice anterior contém valor menor
    # e todo índice posterior contém valor maior ou igual a target.
    return lower


def bisect_right(values: Sequence[int], target: int) -> int:
    """Return the position after all existing occurrences of a target.

    The sequence must already be sorted in ascending order.

    Args:
        values: Sorted integer sequence.
        target: Value whose insertion position is required.

    Returns:
        Index of the right insertion boundary.
    """
    # A busca usa o mesmo intervalo semiaberto de bisect_left. O que muda é o
    # tratamento de um valor exatamente igual a target.
    lower = 0
    upper = len(values)

    # A única diferença para bisect_left está na igualdade. Aqui avançamos
    # depois de valores iguais para obter a borda direita do bloco repetido.
    while lower < upper:
        # Recalculando o meio apenas dentro da região que ainda pode conter a resposta.
        middle = (lower + upper) // 2
        if values[middle] <= target:
            # Valores menores ou iguais devem ficar antes da posição devolvida.
            # Por isso, a região candidata começa depois de middle.
            lower = middle + 1
        else:
            # Um valor maior ainda pode ser o primeiro sucessor de target, então
            # middle permanece incluído no intervalo candidato pelo novo upper.
            upper = middle
    # O encontro dos limites marca a posição posterior à última ocorrência de target.
    return lower
