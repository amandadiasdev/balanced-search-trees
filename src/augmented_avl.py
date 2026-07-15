"""Augmented AVL tree with parent links and order-statistics queries."""

from dataclasses import dataclass, field


@dataclass(slots=True, eq=False)
class Node:
    """Store one key and the metadata derived from its subtree."""

    # A chave define a posição do nó segundo a propriedade de árvore binária
    # de busca. Chaves menores ficam à esquerda e chaves maiores à direita.
    key: int
    # Os dois filhos descrevem a estrutura descendente. O valor None indica
    # que não existe subárvore naquele lado.
    left: "Node | None" = None
    right: "Node | None" = None
    # O ponteiro para o pai permite voltar à raiz sem manter uma pilha externa.
    # repr=False evita uma representação recursiva entre pais e filhos.
    parent: "Node | None" = field(default=None, repr=False)
    # Estes metadados resumem toda a subárvore enraizada no nó. Eles tornam
    # balanceamento, rank, select e agregação eficientes, mas precisam ser
    # atualizados sempre que a estrutura descendente muda.
    height: int = 1
    size: int = 1
    subtree_max: int = field(init=False)

    def __post_init__(self) -> None:
        """Initialize the maximum with the leaf key."""
        # Um nó recém-criado ainda é uma folha. Como sua subárvore contém
        # somente a própria chave, essa chave também é o máximo inicial.
        self.subtree_max = self.key

    def refresh(self) -> None:
        """Recalculate all metadata from the current children."""
        # Uma subárvore ausente possui altura zero. Essa convenção faz uma
        # folha ter altura um e permite aplicar a mesma fórmula a todo nó.
        left_height = self.left.height if self.left else 0
        # A altura do filho direito é obtida do metadado já calculado nele.
        # Portanto, refresh pressupõe que os filhos estejam atualizados.
        right_height = self.right.height if self.right else 0
        # A altura do nó é um nível acima da maior subárvore descendente. Esse
        # valor é usado para calcular o fator de balanceamento AVL.
        self.height = 1 + max(left_height, right_height)
        # O tamanho inclui o próprio nó e todos os nós dos dois lados. O valor
        # zero para um filho ausente mantém a fórmula válida para folhas.
        self.size = 1 + (self.left.size if self.left else 0) + (self.right.size if self.right else 0)
        # O máximo da subárvore precisa considerar três candidatos: a chave
        # local, o máximo já resumido à esquerda e o máximo resumido à direita.
        # Quando um filho não existe, repetir self.key é neutro para o máximo.
        self.subtree_max = max(
            self.key,
            self.left.subtree_max if self.left else self.key,
            self.right.subtree_max if self.right else self.key,
        )


class AugmentedAVLTree:
    """Maintain unique integer keys in an augmented AVL tree."""

    def __init__(self) -> None:
        """Create an empty tree."""
        self.root: Node | None = None
        self.rotation_count = 0

    def __len__(self) -> int:
        """Return the number of stored keys."""
        # size na raiz resume a árvore inteira. Uma árvore sem raiz não possui
        # nós e, por isso, tem tamanho zero.
        return self.root.size if self.root else 0

    def insert(self, key: int) -> bool:
        """Insert a key if it is not already present.

        Args:
            key: Integer key to insert.

        Returns:
            True when the key is inserted, otherwise False.
        """
        # A primeira inserção não exige busca nem rebalanceamento. O Node já
        # nasce com metadados válidos para uma folha e parent igual a None.
        if self.root is None:
            self.root = Node(key)
            return True

        # A busca começa na raiz e mantém em node o último nó existente do
        # caminho. Esse nó será o pai da nova folha e o início do rebalanceamento.
        node = self.root
        while True:
            # A estrutura representa um conjunto. Encontrar a mesma chave
            # encerra a operação sem criar um nó duplicado ou alterar metadados.
            if key == node.key:
                return False
            if key < node.key:
                # Pela propriedade de busca, uma chave menor só pode estar ou
                # ser inserida na subárvore esquerda do nó atual.
                if node.left is not None:
                    # O filho já existe, então a busca continua um nível abaixo.
                    node = node.left
                    continue
                # O primeiro espaço vazio determina a posição da nova folha.
                # parent é preenchido imediatamente para manter o vínculo duplo.
                node.left = Node(key, parent=node)
                break
            # Chegar aqui implica key > node.key, pois igualdade e menor valor
            # já foram tratados. A única direção válida agora é a direita.
            if node.right is not None:
                node = node.right
                continue
            # A folha é conectada ao lado direito e aponta de volta para node.
            node.right = Node(key, parent=node)
            break

        # A inserção pode ter alterado altura, tamanho, máximo e balanceamento
        # de todos os ancestrais. O pai da folha é o ancestral mais baixo afetado.
        self._rebalance_from(node)
        # Retornar True registra que a chave realmente passou a integrar o conjunto.
        return True

    def search(self, key: int) -> bool:
        """Report whether a key is present.

        Args:
            key: Integer key to locate.

        Returns:
            True when the key is stored, otherwise False.
        """
        # _find_node concentra a navegação pela propriedade de busca. A busca
        # pública expõe apenas presença ou ausência, sem revelar o Node interno.
        return self._find_node(key) is not None

    def delete(self, key: int) -> bool:
        """Delete a key when present.

        Args:
            key: Integer key to remove.

        Returns:
            True when the key is removed, otherwise False.
        """
        # Primeiro localizamos o objeto que deverá desaparecer logicamente.
        # Nenhum ponteiro deve ser alterado quando a chave não está presente.
        node = self._find_node(key)
        if node is None:
            return False

        if node.left is not None and node.right is not None:
            # Trocando apenas a chave pelo sucessor. Depois disso, a remoção
            # física acontece em um nó com no máximo um filho.
            # O sucessor é a menor chave maior que node.key. Assim, copiar sua
            # chave preserva a ordenação das duas subárvores do nó original.
            successor = self._minimum(node.right)
            # Somente a chave muda. Os metadados estruturais serão recalculados
            # posteriormente durante a subida de rebalanceamento.
            node.key = successor.key
            # A remoção física passa a mirar o sucessor, que não possui filho
            # esquerdo por definição e, portanto, tem no máximo um filho.
            node = successor

        # Depois da conversão acima, apenas um dos filhos pode existir. Esse
        # filho, se presente, ocupa diretamente a posição do nó removido.
        replacement = node.left if node.left is not None else node.right
        # O pai é salvo antes de desconectar node. Ele é o primeiro ponto cujo
        # resumo de subárvore pode ter diminuído após a remoção.
        rebalance_start = node.parent
        # A substituição atualiza tanto o ponteiro descendente do pai quanto o
        # ponteiro parent do filho substituto.
        self._replace_subtree(node, replacement)
        # Limpando os vínculos do nó removido para que ele deixe de representar
        # qualquer relação estrutural com a árvore ainda viva.
        node.left = None
        node.right = None
        node.parent = None
        # A remoção pode reduzir alturas e provocar rotações em vários ancestrais.
        self._rebalance_from(rebalance_start)
        # True informa que uma chave existente foi efetivamente removida.
        return True

    def rank(self, key: int) -> int:
        """Count stored keys strictly smaller than a key.

        Args:
            key: Integer boundary for the count.

        Returns:
            Number of stored keys smaller than the boundary.
        """
        # result acumula subárvores completas que já sabemos conter somente
        # valores menores que key.
        result = 0
        # A navegação começa na raiz e descarta metade da árvore a cada passo.
        node = self.root
        while node is not None:
            if key <= node.key:
                # O nó atual e toda a subárvore direita são maiores ou iguais
                # ao limite. Nenhum deles pode contribuir para o rank.
                node = node.left
            else:
                # Todos os nós da subárvore esquerda e o nó atual são menores
                # que key. O metadado size permite contá-los em tempo constante.
                result += 1 + (node.left.size if node.left else 0)
                # Após contar o nó e o lado esquerdo, apenas o lado direito
                # ainda pode conter valores menores que key.
                node = node.right
        # Ao alcançar None, todas as regiões relevantes já foram contabilizadas.
        return result

    def select(self, index: int) -> int:
        """Return the key at a zero-based sorted position.

        Args:
            index: Zero-based position in sorted order.

        Returns:
            Key stored at the requested position.

        Raises:
            IndexError: If the index is outside the tree.
        """
        # Validar antes da navegação evita um término ambíguo em None e deixa
        # explícito que select aceita somente posições existentes.
        if index < 0 or index >= len(self):
            raise IndexError(f"index {index} is outside a tree of size {len(self)}")
        # O índice é reinterpretado em relação à raiz de cada subárvore visitada.
        node = self.root
        while node is not None:
            # left_size também é a posição ordenada do nó dentro de sua própria
            # subárvore, pois todas as chaves à esquerda são menores.
            left_size = node.left.size if node.left else 0
            if index == left_size:
                # A quantidade de predecessores coincide com a posição desejada.
                return node.key
            if index < left_size:
                # A posição pertence inteiramente à subárvore esquerda e não
                # precisa ser ajustada ao descer.
                node = node.left
            else:
                # Descartando a subárvore esquerda e o nó atual antes de
                # continuar a busca pela posição na subárvore direita.
                index -= left_size + 1
                node = node.right
        # Este ponto só seria alcançado se size ou a navegação estivessem
        # inconsistentes, pois o intervalo do índice já foi validado.
        raise AssertionError("valid index was not found")

    def range_agg(self, lower: int, upper: int) -> int | None:
        """Return the maximum key in an inclusive interval.

        Args:
            lower: Inclusive lower bound.
            upper: Inclusive upper bound.

        Returns:
            Greatest stored key inside the interval, or None when empty.

        Raises:
            ValueError: If the lower bound is greater than the upper bound.
        """
        # Um intervalo invertido não representa uma consulta fechada válida.
        if lower > upper:
            raise ValueError(f"lower bound {lower} is greater than upper bound {upper}")

        # None representa que nenhum valor dentro do intervalo foi encontrado.
        result = None
        # A busca procura o maior candidato válido, não todos os elementos do intervalo.
        node = self.root
        while node is not None:
            # Se nem o maior valor desta subárvore alcança lower, nenhuma
            # continuação abaixo de node pode responder à consulta.
            if node.subtree_max < lower:
                # O resumo prova que toda a subárvore está abaixo do intervalo.
                break
            if node.key > upper:
                # O nó e todo o lado direito excedem upper. Somente a esquerda
                # ainda pode conter uma chave pertencente ao intervalo.
                node = node.left
            elif node.key < lower:
                # O nó e todo o lado esquerdo são menores que lower. A busca
                # continua à direita, onde as chaves são maiores.
                node = node.right
            else:
                # Guardando o candidato e seguindo à direita, onde só podem
                # existir chaves maiores e, portanto, respostas melhores.
                result = node.key
                node = node.right
        # O último candidato salvo é o maior valor observado dentro de [lower, upper].
        return result

    def assert_valid(self) -> None:
        """Verify ordering, parent links, AVL balance, and metadata.

        Raises:
            AssertionError: If any structural invariant is violated.
        """
        # A validação recalcula os metadados a partir da estrutura, em vez de
        # confiar nos valores armazenados que ela pretende verificar.
        calculated_size = self._validate_node(self.root, None, None, None, set())[1]
        # Esta checagem final compara o total independente com a interface len.
        if calculated_size != len(self):
            raise AssertionError(f"tree size is {len(self)}, expected {calculated_size}")

    def _replace_subtree(self, old_root: Node, new_root: Node | None) -> None:
        """Replace one subtree while preserving the link to its parent.

        Args:
            old_root: Root currently attached to the tree.
            new_root: Root that will take its place, or None.
        """
        parent = old_root.parent
        # Reconectando primeiro o pai da subárvore. Esta mesma rotina atende
        # tanto remoções quanto rotações e centraliza a manutenção de parent.
        if parent is None:
            # Uma subárvore sem pai é a própria raiz da árvore completa.
            self.root = new_root
        elif parent.left is old_root:
            # Preservando o lado em que old_root estava conectado ao pai.
            parent.left = new_root
        else:
            # Se old_root não era o filho esquerdo, uma árvore válida exige que
            # ele fosse o filho direito do mesmo pai.
            parent.right = new_root
        if new_root is not None:
            # O vínculo ascendente deve refletir imediatamente a nova conexão.
            new_root.parent = parent

    def _find_node(self, key: int) -> Node | None:
        """Find and return a node by key.

        Args:
            key: Integer key to locate.

        Returns:
            Matching node, or None when absent.
        """
        # Cada comparação elimina uma subárvore inteira graças à ordenação BST.
        node = self.root
        while node is not None:
            if key == node.key:
                # Retornar o objeto, em vez de apenas bool, permite que delete
                # altere seus vínculos posteriormente.
                return node
            # Chaves menores só podem estar à esquerda; maiores, à direita.
            node = node.left if key < node.key else node.right
        # Alcançar um filho vazio prova que a chave não está armazenada.
        return None

    @staticmethod
    def _minimum(node: Node) -> Node:
        """Return the smallest node in a non-empty subtree.

        Args:
            node: Root of the subtree.

        Returns:
            Leftmost node in the subtree.
        """
        # A menor chave de uma BST é encontrada seguindo filhos esquerdos até
        # o primeiro nó que não possua outro valor menor abaixo dele.
        while node.left is not None:
            node = node.left
        return node

    def _rotate_left(self, node: Node) -> Node:
        """Rotate a right-heavy subtree to the left.

        Args:
            node: Root of the unbalanced subtree.

        Returns:
            New root of the local subtree.
        """
        # Uma rotação à esquerda exige que o filho direito suba e se torne o
        # novo topo local. Esse filho recebe o nome pivot.
        pivot = node.right
        if pivot is None:
            # Sem filho direito, a transformação não possui pivô e indicaria
            # uso incorreto da rotina interna.
            raise AssertionError("left rotation requires a right child")
        # A antiga subárvore esquerda do pivô precisa ser preservada durante a rotação.
        moved_subtree = pivot.left
        # A antiga raiz ocupa o lado esquerdo do pivô. A subárvore que estava
        # ali passa para o único espaço livre, o lado direito da antiga raiz.
        self._replace_subtree(node, pivot)
        # O pivô ocupa a posição antiga de node e passa a tê-lo como filho esquerdo.
        pivot.left = node
        # O vínculo de retorno de node precisa acompanhar a nova relação descendente.
        node.parent = pivot
        # moved_subtree contém valores maiores que node e menores que pivot,
        # portanto sua única posição válida é o lado direito de node.
        node.right = moved_subtree
        if moved_subtree is not None:
            # A subárvore transferida agora volta para node, não mais para pivot.
            moved_subtree.parent = node
        # node foi rebaixado e deve ser atualizado antes de pivot, pois os
        # metadados do pivô dependem dos metadados já corretos de seus filhos.
        node.refresh()
        pivot.refresh()
        # A contagem é uma métrica experimental e não interfere na estrutura.
        self.rotation_count += 1
        return pivot

    def _rotate_right(self, node: Node) -> Node:
        """Rotate a left-heavy subtree to the right.

        Args:
            node: Root of the unbalanced subtree.

        Returns:
            New root of the local subtree.
        """
        # A rotação à direita espelha a rotação à esquerda: o filho esquerdo
        # sobe para ocupar o topo local.
        pivot = node.left
        if pivot is None:
            # A ausência do filho esquerdo torna a rotação estruturalmente impossível.
            raise AssertionError("right rotation requires a left child")
        # O lado direito do pivô será transferido para não ser perdido.
        moved_subtree = pivot.right
        # Esta é a operação espelhada de rotate_left. Cada ponteiro de filho
        # alterado recebe imediatamente o parent correspondente.
        self._replace_subtree(node, pivot)
        # O antigo topo passa a ser filho direito do pivô que acabou de subir.
        pivot.right = node
        node.parent = pivot
        # Os valores transferidos estão entre pivot e node e pertencem ao lado esquerdo de node.
        node.left = moved_subtree
        if moved_subtree is not None:
            moved_subtree.parent = node
        # Atualizando primeiro o nó rebaixado e depois o pivô que depende dele.
        node.refresh()
        pivot.refresh()
        self.rotation_count += 1
        return pivot

    def _rebalance_from(self, node: Node | None) -> None:
        """Refresh and rebalance every ancestor up to the root.

        Args:
            node: Lowest ancestor whose subtree may have changed.
        """
        # O ponteiro parent substitui uma pilha explícita de ancestrais. Cada
        # iteração sobe exatamente um nível em direção à raiz.
        while node is not None:
            # Filhos já estão corretos quando o percurso alcança node, então os
            # resumos locais podem ser recalculados de baixo para cima.
            node.refresh()
            # Fator positivo indica maior altura à esquerda; negativo, à direita.
            balance = self._balance(node)
            if balance > 1:
                # Diferença maior que um viola o invariante AVL no lado esquerdo.
                left_child = node.left
                if left_child is None:
                    # Um fator positivo maior que um sem filho esquerdo revelaria
                    # metadados ou vínculos corrompidos.
                    raise AssertionError("left-heavy node has no left child")
                if self._balance(left_child) < 0:
                    # Caso esquerda-direita: alinhando o filho antes da
                    # rotação principal sobre o nó desbalanceado.
                    self._rotate_left(left_child)
                # Após eventual alinhamento do filho, a rotação à direita
                # restaura a diferença de alturas permitida.
                node = self._rotate_right(node)
            elif balance < -1:
                # Diferença menor que menos um representa excesso no lado direito.
                right_child = node.right
                if right_child is None:
                    raise AssertionError("right-heavy node has no right child")
                if self._balance(right_child) > 0:
                    # Caso direita-esquerda: alinhando o filho antes da
                    # rotação principal sobre o nó desbalanceado.
                    self._rotate_right(right_child)
                # A rotação à esquerda corrige o topo local desbalanceado.
                node = self._rotate_left(node)
            # Depois de uma rotação, node aponta para o novo topo local. Subir
            # pelo parent correto continua a atualização no ancestral seguinte.
            node = node.parent

    @staticmethod
    def _balance(node: Node | None) -> int:
        """Return the AVL balance factor for a node.

        Args:
            node: Node to inspect, or None.

        Returns:
            Left height minus right height, or zero for None.
        """
        if node is None:
            # Uma subárvore vazia não favorece nenhum dos dois lados.
            return 0
        # A AVL aceita somente resultados -1, 0 ou 1 em uma árvore válida.
        return (node.left.height if node.left else 0) - (node.right.height if node.right else 0)

    @classmethod
    def _validate_node(
        cls,
        node: Node | None,
        lower: int | None,
        upper: int | None,
        expected_parent: Node | None,
        seen: set[int],
    ) -> tuple[int, int, int | None]:
        """Validate a subtree and return independently calculated metadata.

        Args:
            node: Root of the subtree to validate.
            lower: Exclusive lower key bound, or None.
            upper: Exclusive upper key bound, or None.
            expected_parent: Parent that the node must reference.
            seen: Node identities already visited.

        Returns:
            Calculated height, size, and maximum.

        Raises:
            AssertionError: If an invariant is violated.
        """
        if node is None:
            # O caso-base fornece os elementos neutros usados nas fórmulas do pai.
            return 0, 0, None
        identity = id(node)
        # Usando a identidade do objeto, e não a chave, para detectar tanto
        # ciclos quanto um mesmo nó ligado em duas posições da árvore.
        if identity in seen:
            raise AssertionError(f"node {node.key} appears more than once or forms a cycle")
        # Registrar antes da recursão permite detectar o retorno ao próprio nó.
        seen.add(identity)
        if node.parent is not expected_parent:
            # Cada aresta descendente deve possuir a aresta ascendente correspondente.
            raise AssertionError(f"node {node.key} has an incorrect parent")
        if lower is not None and node.key <= lower:
            # lower é exclusivo porque chaves duplicadas também são inválidas.
            raise AssertionError(f"node {node.key} violates lower bound {lower}")
        if upper is not None and node.key >= upper:
            # Todo descendente esquerdo deve permanecer estritamente abaixo do ancestral.
            raise AssertionError(f"node {node.key} violates upper bound {upper}")

        # Os limites são estreitados ao descer. A chave atual vira o limite
        # superior à esquerda e o limite inferior à direita.
        left_height, left_size, left_max = cls._validate_node(node.left, lower, node.key, node, seen)
        right_height, right_size, right_max = cls._validate_node(node.right, node.key, upper, node, seen)
        # Recalculando os três metadados sem usar height, size ou subtree_max do nó atual.
        height = 1 + max(left_height, right_height)
        size = 1 + left_size + right_size
        # Filhos vazios retornam None e são removidos antes da chamada de max.
        subtree_max = max(value for value in (node.key, left_max, right_max) if value is not None)
        if abs(left_height - right_height) > 1:
            # Esta comparação usa alturas recalculadas, evitando validar um
            # metadado incorreto com outro metadado igualmente incorreto.
            raise AssertionError(f"node {node.key} is not AVL-balanced")
        if (node.height, node.size, node.subtree_max) != (height, size, subtree_max):
            # A tupla permite relatar de uma vez qual resumo armazenado divergiu
            # de sua recomputação independente.
            raise AssertionError(
                f"node {node.key} metadata is {(node.height, node.size, node.subtree_max)}, "
                f"expected {(height, size, subtree_max)}"
            )
        # O pai usa esses valores recalculados para validar seu próprio resumo.
        return height, size, subtree_max
