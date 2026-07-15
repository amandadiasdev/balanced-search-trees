# Checklist de consolidação dos resultados

Este checklist registra a consolidação da bateria executada no testbed definitivo.

- [x] Confirmar o runtime registrado pelo CSV: CPython 3.13.5, compilado com Clang 20.1.4. A versão do `uv` foi retirada da tabela porque não foi registrada nos resultados.
- [x] Confirmar 140 execuções bem-sucedidas e únicas, 70 pares AVL/lista e 14 rastros completos.
- [x] Remover as 22 tentativas iniciais com `status=erro`, todas substituídas posteriormente por execuções bem-sucedidas com o mesmo `run_id`.
- [x] Regenerar `speedup-escala-ordem.svg` e `impacto-theta-remocao.svg` com o CSV definitivo.
- [x] Converter os dois SVGs para os PDFs utilizados pelo relatório.
- [x] Substituir médias, p50 e p99 da Tabela 2.
- [x] Revisar as razões de inserção, o workload completo e os ganhos sob `sorted`.
- [x] Revisar as razões, o p99 e os dados estruturais sob `shuffle`.
- [x] Revisar os intervalos de latência e a redução percentual associada a $\theta$.
- [x] Atualizar a síntese quantitativa das considerações finais.
- [x] Conferir títulos, legendas, unidades e referências cruzadas das figuras e tabelas.
- [x] Confirmar que nenhum marcador `REVISAO_FINAL` permanece em `report.tex`.
- [x] Compilar o relatório e inspecionar visualmente as seis páginas do PDF.
- [x] Atualizar e validar o HTML didático em viewports desktop e mobile.

Resultado da auditoria: 28,22 milhões de operações medidas, sem falhas residuais, pares incompletos, divergências de oráculo ou inconsistências determinísticas.
