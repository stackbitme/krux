# Stackbit 1248 Scanner - Changelog e Progresso

**Versão Atual:** v1.2.0
**Data:** 31 de Janeiro de 2026
**Repositório:** odudex/krux (branch: embed_fire)
**Dispositivo:** maixpy_embed_fire (Embed Fire / WonderK)

---

## Resumo

Implementação de scanner de câmera para placas Stackbit 1248, permitindo leitura automática de mnemonics BIP39 gravados em metal usando codificação binária 1-2-4-8.

---

## Estrutura da Grade

### Stackbit 1248 Full (85.6mm × 53.98mm)
- **Layout:** 16 colunas × 12 linhas
- **Aspecto:** 1.586 (range: 1.4 - 1.8)
- **Capacidade:** 12 palavras por lado (24 total usando ambos os lados)
- **Estrutura por grupo:**
  - Coluna 0/8: Indexador (números 1, 7, 13, 19)
  - Coluna 1/9: Milhar (posições superior=1, inferior=2)
  - Colunas 2-7/10-15: Três pares de codificação 1-2-4-8 (centenas, dezenas, unidades)

### Detecção Automática
- Usa blob detection para encontrar a placa metálica (região brilhante)
- Calcula aspect ratio para determinar tipo de placa
- Sobrepõe grade 16×12 dinamicamente sobre a placa detectada
- **SEM offsets de borda** (gabarito removido após perfuração)

---

## Métodos de Detecção de Pontos Marcados

### 1. Threshold Adaptativo (Baseado em Luminância)
```python
relative_threshold = self.blob_otsu - 30
is_punched = cell_lum < relative_threshold
```
- Usa histograma da imagem (`blob_otsu`) como linha de base
- Detecta células 30 pontos mais escuras que a linha de base
- Adapta automaticamente a diferentes condições de iluminação

### 2. Detecção de Blobs Circulares (Baseado em Forma)
```python
blobs = img.find_blobs(
    blob_threshold,
    roi=(x, y, w, h),
    pixels_threshold=int(w * h * 0.1),
    area_threshold=int(w * h * 0.08),
    merge=True
)
# Verifica roundness > 0.3
```
- Procura por blobs escuros e arredondados dentro de cada célula
- Threshold: pelo menos 40 pontos mais escuro que a média da célula
- Requer mínimo 10% da área da célula
- Verifica circularidade (roundness > 0.3)

### 3. Detecção de Contraste (Alto Desvio Padrão)
```python
std = stats.l_stdev()
if std > 25:
    is_punched = True
```
- Analisa desvio padrão da luminância na célula
- Alto desvio indica presença de ponto escuro
- Threshold: std > 25

**Lógica Combinada:** Ponto detectado se QUALQUER um dos 3 métodos indicar presença de marcação (OR lógico).

---

## Visualização da Grade após Leitura

### Funcionalidade Implementada (30/01/2026 - 14:32)

Após o usuário clicar/tocar na tela para realizar a leitura:

1. **Captura e Preservação da Imagem**
   - O frame da câmera é capturado e copiado antes de parar o sensor
   - Mantém a mesma imagem exata que estava sendo exibida durante a detecção

2. **Visualização Gráfica da Grade**
   - Exibe a mesma grade 16×12 usada durante a captura
   - Mantém modo landscape (orientação horizontal da câmera)
   - Desenha todas as linhas da grade (brancas)
   - Destaca colunas indexadoras (0 e 8) com linhas mais grossas

3. **Marcação dos Pontos Detectados**
   - **Círculos vermelhos preenchidos** nos pontos onde detectou marcação
   - Posicionados no centro de cada célula
   - Raio = 1/3 da menor dimensão da célula
   - **Pula colunas indexadoras** (0 e 8) - não desenha pontos lá
   - Usa `lcd.RED` com `thickness=-1` (preenchido)

4. **Interação do Usuário**
   - Aguarda 1 segundo para visualização
   - Espera usuário pressionar botão para continuar
   - Após confirmação, muda para portrait e mostra lista de palavras

### Código Implementado

```python
def _show_grid_visualization(self, grid, img):
    """Show visual representation of the grid with detected punches

    Displays the same grid overlay used during camera capture,
    but with red dots marking the detected punches.
    """
    # Create a copy of the image to draw on
    display_img = img.copy()

    # Draw grid lines (16×12)
    # Draw rectangle outline + vertical + horizontal lines

    # Draw red dots for detected punches
    for row_idx in range(12):
        for col_idx in range(16):
            # Skip indexador columns (0 and 8)
            if col_idx == 0 or col_idx == 8:
                continue

            if grid[row_idx][col_idx]:  # If punched
                # Calculate center position
                center_x = x + w // 2
                center_y = y + h // 2
                radius = min(w, h) // 3

                # Draw filled red circle
                display_img.draw_circle(center_x, center_y, radius, lcd.RED, thickness=-1)

    # Display the image
    lcd.display(display_img)

    # Wait for user confirmation
    self.ctx.input.wait_for_button()
```

### Fluxo de Uso

1. **Usuário posiciona placa** sob câmera
2. **Aguarda alinhamento** automático da grade 16×12
3. **Observa marcações em tempo real** (quadrados pretos com borda)
4. **Clica/toca na tela** quando satisfeito com o alinhamento
5. **Vê grade visual** com círculos vermelhos nos pontos detectados
6. **Pressiona botão** para confirmar visualização
7. **Revisa lista de palavras** decodificadas

### Benefícios

- ✅ **Feedback visual imediato** de quais pontos foram detectados
- ✅ **Consistência visual** com a grade de captura
- ✅ **Fácil verificação** antes de prosseguir para palavras
- ✅ **Mantém contexto espacial** da placa original
- ✅ **Permite identificar** problemas de detecção rapidamente

---

## Visualização ASCII - Formato e Espaçamento (30/01/2026 - 22:33)

### Formato Implementado

Após a leitura da placa, o sistema exibe uma representação ASCII usando colchetes:
- `[x]` = célula com marcação detectada
- `[ ]` = célula vazia (sem marcação)

### Estrutura de Espaçamento

Cada linha de palavra exibe 8 colunas com espaçamento preciso:

```
[idx]  [mil][c8][c4]  [d8][d4]  [u8][u4]
```

**Detalhamento:**
- **Coluna 0:** Indexador - 2 espaços após `]`
- **Coluna 1:** Milhar - sem espaço após `]`
- **Colunas 2-3:** Par Centena (8/2 e 4/1) - 2 espaços após o par
- **Colunas 4-5:** Par Dezena (8/2 e 4/1) - 2 espaços após o par
- **Colunas 6-7:** Par Unidade (8/2 e 4/1) - sem espaço após o par

### Exemplo Real

```
Página 1 - Grupo Esquerdo (Palavras 1-6):
1.  [x]  [ ][x]  [x][ ]  [ ][ ]
    [ ]  [ ][ ]  [ ][x]  [x][ ]
```

No exemplo acima:
- Indexador: `1.` (linha superior)
- Milhar: `[x]` = 2
- Centena: `[ ][x]` = 0 + 4 = 4
- Dezena: `[x][ ]` = 8 + 0 = 8
- Unidade: `[ ][ ]` = 0 + 0 = 0

Resultado: palavra #1 = 2480 da wordlist BIP39

### Exibição em Duas Páginas

**Página 1:** Colunas 0-7 (Palavras 1-6)
**Página 2:** Colunas 8-15 (Palavras 7-12)

Cada página mostra 6 palavras (12 linhas: 2 linhas por palavra).

---

## Arquivos Modificados

### 1. `/src/krux/pages/stack_1248_scanner.py` (718 linhas)
**Novo arquivo criado**

Principais componentes:
- `class StackbitScanner(Page)`: Scanner principal
- `_detect_plate(img)`: Detecção automática da placa via blob detection
- `_create_grid_over_rect(rect)`: Cria grade 16×12 sobre placa detectada
- `_draw_grid(img, rect)`: Desenha sobreposição de grade na câmera
- `_read_cell(img, x, y, w, h)`: Lê célula individual com 3 métodos de detecção
- `_decode_word_from_row_pair(img, word_idx, col_offset)`: Decodifica palavra usando 1-2-4-8
- `_decode_all_words(img)`: Decodifica todas as 12 palavras
- `_read_all_grid_cells(img, rect)`: Lê todas as células da grade 16×12
- `_create_16x12_grid_regions(rect)`: Cria regiões uniformes para grade 16×12
- `_show_ascii_grid(grid)`: Visualização ASCII com colchetes e espaçamento preciso
- `_show_words_for_confirmation(words)`: Tela de confirmação com lista de palavras
- `scanner(w24=False)`: Loop principal com trigger manual (clique/toque)

### 2. `/src/krux/pages/mnemonic_loader.py`
**Modificações:**
- `load_key_from_1248()`: Adicionado submenu "Manual Entry" vs "Scan with Camera"
- `load_key_from_1248_manual()`: Entrada manual (funcionalidade existente)
- `load_key_from_1248_scan()`: Nova função para scanner de câmera

### 3. `/src/krux/pages/stack_1248.py`
**Modificações:**
- Adicionados imports: `lcd`, `image`, `sensor`, `time`, `BINARY_GRID_MODE`, `wdt`

---

## Funcionalidades Implementadas

### Interface do Usuário
1. **Menu Integration:** Submenu em "Load Mnemonic → Stackbit 1248"
2. **Trigger Manual:** Usuário clica na tela para realizar leitura
3. **Marcação Visual em Tempo Real:**
   - Quadrados com borda preta marcam pontos detectados
   - Pula colunas indexadoras (0 e 8)
4. **Visualização de Grade:** Representação em texto com X (detectado), | (indexador), . (vazio)
5. **Tela de Confirmação:** Lista scrollável com as 12 palavras lidas

### Processo de Leitura
1. Posicionar placa sob câmera
2. Aguardar detecção e alinhamento automático da grade
3. Observar marcações em tempo real dos pontos detectados
4. Clicar/tocar na tela quando pronto
5. Revisar visualização da grade
6. Confirmar lista de 12 palavras

### Suporte a Variantes
- **Stackbit 1248 Full:** Lê 12 palavras de uma vez (ambas as colunas)
- **Detecção automática** via aspect ratio
- **Grade adaptativa** se ajusta ao tamanho detectado

---

## Build Information

**Firmware Atual: v1.0.0**
- **Arquivo:** `/build/kboot.kfpkg`
- **Tamanho:** 847KB
- **Timestamp:** 31 Jan 2026, 13:54
- **Device:** maixpy_embed_fire
- **Mudanças:** Correção de consistência na leitura de células (amostragem centralizada)

**Docker Build:**
- Base: `gcc:9.5.0-bullseye`
- Toolchain: kendryte-gnu-toolchain v8.2.0-20190409
- CMake: 3.21.0
- Python: 3.9 (venv: /kruxenv)

**Comando de Flash:**
```bash
sudo /Users/valandro/Downloads/krux_odudex/build/ktool-mac \
  -B dan -b 1500000 \
  -p /dev/cu.usbserial-110 \
  /Users/valandro/Downloads/krux_odudex/build/kboot.kfpkg
```

---

## Configuração do Ambiente

### Dependências Docker
- kendryte-gnu-toolchain (RISC-V)
- CMake 3.21.0
- Python 3.9 com venv
- Bibliotecas: astor, pyserial==3.4, kconfiglib

### Vendor Dependencies (Git Submodules)
- embit (Bitcoin library)
- urtypes (UR types)
- foundation-ur-py (UR encoding)

---

## Próximos Passos / Melhorias Futuras

### Testado
- [x] Sintaxe do código validada
- [x] Build compilado com sucesso
- [x] Flash no dispositivo realizado

### Pendente de Teste
- [ ] Teste em dispositivo físico com placa real
- [ ] Ajuste fino dos thresholds se necessário
- [ ] Validação com diferentes condições de iluminação
- [ ] Teste com diferentes cores de marcador

### Possíveis Melhorias
- [ ] Suporte para Stackbit 1248 Mini (aspect ratio ~0.793)
- [ ] Feedback de progresso durante leitura
- [ ] Modo de calibração manual de thresholds
- [ ] Suporte a 24 palavras (ambos os lados)

---

## Notas Técnicas

### Codificação 1-2-4-8
Cada dígito decimal (0-9) é codificado usando duas colunas:
- Coluna esquerda: 8 (superior), 2 (inferior)
- Coluna direita: 4 (superior), 1 (inferior)

Exemplos:
- 0 = (sem marcas)
- 1 = marca na posição 1
- 5 = marcas nas posições 4 + 1
- 7 = marcas nas posições 4 + 2 + 1
- 9 = marcas nas posições 8 + 1

### Número BIP39
- Milhar: 0, 1 ou 2
- Centenas, Dezenas, Unidades: 0-9
- Range válido: 1-2048 (mapeia para wordlist BIP39)

---

## Créditos

- **Formato Stackbit 1248:** @valandro
- **Implementação do Scanner:** Baseado na arquitetura do TinySeed scanner do Krux
- **Repositório:** odudex/krux (fork com suporte Embed Fire)
- **Website:** https://stackbit.me
- **Tutorial:** https://stackbit.me/tutorial-stackbit-1248/

---

## Estado Final

✅ **Scanner implementado e funcionando**
✅ **Firmware compilado com sucesso (847KB)**
✅ **Flash realizado no dispositivo**
✅ **Detecção multi-método (threshold + forma + contraste)**
✅ **Visualização gráfica com pontos vermelhos**
✅ **Interface de usuário completa**
✅ **Código documentado e organizado**
✅ **Consistência entre detecção ao vivo e leitura final**

**Última atualização:** 31/01/2026 às 18:05
**Versão do firmware:** v1.1.0 - kboot.kfpkg (848KB)

### Histórico de Versões

| Versão | Data | Hora | Tamanho | Mudança Principal |
|--------|------|------|---------|-------------------|
| - | 30/01/2026 | 14:08 | 846KB | Detecção multi-método implementada |
| - | 30/01/2026 | 14:32 | 846KB | Visualização gráfica com círculos vermelhos |
| - | 30/01/2026 | 14:51 | 846KB | Grade com fundo preto, linhas brancas e pontos vermelhos |
| - | 30/01/2026 | 14:59 | 846KB | **FIX:** Adicionado import do módulo `image` |
| - | 30/01/2026 | 15:13 | 846KB | **FIX:** Implementado método `_read_all_grid_cells` |
| - | 30/01/2026 | 15:27 | 846KB | **FIX:** Grade 16×12 uniforme para visualização correta |
| - | 30/01/2026 | 15:35 | 846KB | **FIX:** Removido método `_read_all_grid_cells` duplicado |
| - | 30/01/2026 | 16:00 | 847KB | Visualização ASCII com colchetes (2 páginas: esq/dir) |
| - | 30/01/2026 | 22:33 | 847KB | **FIX:** Corrigido espaçamento ASCII para formato preciso |
| - | 31/01/2026 | 13:33 | 846KB | **FIX:** Espaçamento entre palavras + ponto em 10/11/12 |
| **v1.0.0** | 31/01/2026 | 13:54 | 847KB | **FIX:** Amostragem centralizada consistente (70%×60%) |
| - | 31/01/2026 | 15:30 | - | **FEAT:** Detecção melhorada para placa 85×54mm |
| - | 31/01/2026 | 15:30 | - | **FEAT:** Visualização Stackbit 1248 após ASCII (6 palavras/pág) |
| **v1.1.0** | 31/01/2026 | 18:05 | 848KB | **FIX:** Correção do mapeamento 1-2-4-8 na decodificação |
| **v1.2.0** | 31/01/2026 | 21:46 | 848KB | **FEAT:** Carregamento automático da wallet após scan |

### Notas da Versão v1.0.0

**Problema corrigido:** Inconsistência na detecção entre a visualização ao vivo (câmera) e a leitura final (ASCII).

**Causa:** A função `_read_all_grid_cells` estava lendo a célula **inteira**, enquanto a detecção ao vivo usava uma **amostra centralizada** (70% largura, 60% altura). Isso causava falsos positivos na leitura final porque incluía bordas e linhas da grade.

**Solução:** Aplicar a mesma amostragem centralizada em `_read_all_grid_cells`:
```python
# 60% altura, 20% offset do topo
sample_h = int(h * 0.6)
sample_y = y + int(h * 0.2)

# 70% largura, 15% offset da esquerda
sample_w = int(w * 0.7)
sample_x = x + int(w * 0.15)
```

Agora a detecção ao vivo e a leitura final usam a mesma ROI (região de interesse), garantindo consistência visual e funcional.

### Mudanças em Desenvolvimento (pós v1.0.0)

**1. Detecção de Placa Melhorada (85×54mm)**
- Aspect ratio alvo: 85/54 = 1.574 (proporção exata da placa)
- Tolerância expandida: ±0.25 (permite 1.324 a 1.824)
- Threshold mais baixo para detectar melhor as bordas
- Margem de 5px permite placa parcialmente fora do frame
- Score considera área do blob (maior é melhor)

**2. Visualização Stackbit 1248**
- Nova tela após a grade ASCII
- Mostra 6 palavras por página (igual ao backup mnemonic > stackbit 1248)
- Formato visual:
  - Número da palavra (1-12) em fundo cinza
  - Grade 1-2-4-8 com quadrados destacados
  - Número de 4 dígitos em ciano
  - Palavra BIP39 em cinza
- Duas páginas: palavras 1-6 e 7-12

### Notas da Versão v1.1.0

**Problema corrigido:** A visualização Stackbit 1248 mostrava números/palavras incorretos.

**Causa:** O mapeamento dos bits 1-2-4-8 na função `_decode_numbers_from_grid` estava invertido.

**Antes (errado):**
```python
# Left column: upper=8, lower=2
# Right column: upper=4, lower=1
val_8 = 8 if grid[row_upper][col_left] else 0
val_2 = 2 if grid[row_lower][col_left] else 0
val_4 = 4 if grid[row_upper][col_right] else 0
val_1 = 1 if grid[row_lower][col_right] else 0
```

**Depois (correto):**
```python
# Layout real: upper=1,2 lower=4,8 para cada par
# Left column: upper=1, lower=4
# Right column: upper=2, lower=8
val_1 = 1 if grid[row_upper][col_left] else 0
val_4 = 4 if grid[row_lower][col_left] else 0
val_2 = 2 if grid[row_upper][col_right] else 0
val_8 = 8 if grid[row_lower][col_right] else 0
```

**Mudanças na v1.1.0:**
1. Detecção de placa melhorada para 85×54mm (aspect ratio 1.574)
2. Visualização Stackbit 1248 após grade ASCII (6 palavras/página)
3. Correção do mapeamento 1-2-4-8 para decodificação correta

### Notas da Versão v1.2.0

**Nova funcionalidade:** Carregamento automático da wallet após scan bem-sucedido.

**Fluxo atualizado:**
1. Usuário posiciona placa sob câmera
2. Clica/toca na tela para realizar leitura
3. Visualiza grade ASCII com pontos detectados
4. Visualiza tabela Stackbit 1248 com palavras decodificadas
5. **NOVO:** Se palavras válidas, prompt "Load wallet?"
6. **NOVO:** Se confirmar, retorna lista de 12 palavras para carregar a seed

**Mudanças técnicas:**
- Novo método `_validate_and_get_words(grid)`: valida números 1-2048 e converte para palavras BIP39
- Método `scanner()` agora retorna lista de palavras (como `enter_1248()`)
- Após mostrar visualização Stackbit 1248, pergunta ao usuário se deseja carregar a wallet
- Se usuário confirmar, retorna as palavras para o fluxo normal de carregamento
- Se usuário recusar ou palavras inválidas, volta para modo de scan

**Comportamento:**
- Scanner funciona igual ao `enter_1248()` manual: retorna lista de palavras válidas ou `None`
- Integração transparente com o resto do sistema de carregamento de mnemonic
- Usuário pode escolher reescanear se resultado não estiver correto
