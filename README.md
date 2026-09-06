# Monitor de Preços — Amazon & Mercado Livre

Monitora os preços dos links que você cadastrar, roda sozinho todo dia (via GitHub Actions,
de graça) e te avisa por e-mail quando algum preço cair. Gera também um site (index.html)
com o histórico de cada produto.

## Como colocar no ar (uma vez só)

### 1. Crie um repositório no GitHub
Suba esta pasta inteira para um repositório novo (pode ser privado).

### 2. Adicione seus links
Edite `links.json` e coloque os links dos produtos da Amazon e do Mercado Livre que você
quer acompanhar, um por linha, entre aspas:

```json
[
  "https://www.mercadolivre.com.br/produto-x/p/MLB123",
  "https://www.amazon.com.br/dp/B0XXXXX"
]
```

### 3. Configure o e-mail de alerta (opcional, mas é o que você pediu)
No GitHub: **Settings → Secrets and variables → Actions → New repository secret**, crie:

| Nome | Valor |
|---|---|
| `SMTP_USER` | seu e-mail do Gmail |
| `SMTP_PASS` | uma **senha de app** do Gmail (não é a senha normal — gere em myaccount.google.com/apppasswords) |
| `SMTP_TO` | para qual e-mail mandar o alerta (pode ser o mesmo `SMTP_USER`) |

### 4. Ative o GitHub Pages (para ver o site)
**Settings → Pages → Source: branch `main`, pasta `/ (root)`**.
Depois de rodar pela primeira vez, seu dashboard fica em:
`https://SEU-USUARIO.github.io/NOME-DO-REPO/`

### 5. Rode manualmente a primeira vez
Vá em **Actions → Monitor de Precos → Run workflow**. Isso já verifica os preços,
gera o `index.html` e envia e-mail se algo tiver caído (na primeira vez não vai
disparar alerta, pois ainda não há preço anterior para comparar).

Depois disso, ele roda **sozinho todo dia às 09h (horário de Brasília)**.

## Rodando na sua máquina (teste local)

```bash
pip install -r requirements.txt
python price_monitor.py
```

Isso gera/atualiza `history.json` e `index.html` na pasta — abra o `index.html` no
navegador para ver o dashboard.

## Usando sem instalar Python (executável .exe)

Você pode gerar um `.exe` que roda no Windows sem precisar instalar Python — o
próprio GitHub monta ele pra você:

1. Vá na aba **Actions** do repositório
2. Clique em **Gerar Executavel Windows** (barra lateral esquerda)
3. Clique em **Run workflow** e espere ~1–2 minutos
4. Quando terminar, clique na execução e baixe o artefato **monitor-precos-windows**
   (é um .zip contendo o `monitor-precos.exe`)
5. Extraia o `.exe` numa pasta, e coloque nela também os arquivos `links.json` e,
   se quiser receber e-mail, um `config.json` (copie `config.example.json` e
   preencha com seus dados — veja como gerar a senha de app do Gmail na seção acima)
6. Dê **duplo clique no `monitor-precos.exe`**. Ele abre um terminal, verifica os
   preços, compara com outras lojas, atualiza o `index.html` e fecha só quando você
   apertar Enter.

Esse `.exe` roda só quando você clica nele — não fica monitorando sozinho. Se quiser
que rode todo dia automaticamente sem você lembrar, duas opções:
- Deixe o workflow `Monitor de Precos` (o outro, agendado) ativo no GitHub — daí nem
  precisa do .exe, ele já roda na nuvem sozinho; ou
- Agende o `.exe` no **Agendador de Tarefas do Windows** pra rodar 1x por dia.

Toda vez que o `price_monitor.py` for atualizado, rode o workflow **Gerar Executavel
Windows** de novo pra gerar um `.exe` atualizado.

## Comparação com outras lojas

Além de acompanhar o preço do link que você cadastrou, o robô agora **pesquisa o mesmo
produto em outras lojas** (Mercado Livre, Amazon e Magazine Luiza) e mostra no dashboard
qual está mais barata — com uma coroa 🏆 na melhor oferta. Se encontrar em outro lugar
mais de 5% mais barato que o seu link, isso também entra no e-mail de alerta.

A busca usa o título do produto extraído da própria página, então funciona melhor
quando o título é específico (ex: com marca e modelo).

## Limitações importantes

- **Amazon e Magazine Luiza bloqueiam robôs com frequência** (CAPTCHA, IP banido), tanto
  na página do produto quanto na busca. Pode falhar de vez em quando — isso é esperado,
  não é bug. O Mercado Livre usa API pública oficial, então é o mais confiável de todos.
- Se algum site mudar o layout da página ou da busca, os seletores em `price_monitor.py`
  (funções `get_*_price` e `search_*`) podem precisar de ajuste.
- A comparação entre lojas é "melhor esforço": nem sempre o resultado da busca é
  exatamente o mesmo produto (variações de cor/modelo podem aparecer). Sempre confira
  o link antes de comprar.
- Isso é para uso pessoal — evite rodar com muita frequência ou muitos links de uma vez
  para não ser bloqueado.
