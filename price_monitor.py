"""
Monitor de Preços - Amazon & Mercado Livre
--------------------------------------------
Lê os links em links.json, busca o preço atual de cada produto,
compara com o histórico salvo em history.json e, se algum preço
tiver baixado, envia um e-mail de alerta.

No final, gera um dashboard estático (index.html) com o histórico
de cada produto.
"""

import requests
from bs4 import BeautifulSoup
import json
import os
import re
import sys
import smtplib
from email.mime.text import MIMEText
from datetime import datetime

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}

LINKS_FILE = "links.json"
HISTORY_FILE = "history.json"
DASHBOARD_FILE = "index.html"
CONFIG_FILE = "config.json"


def load_local_config():
    """Lê config.json (usado quando roda como .exe local) e joga nas variáveis
    de ambiente, para reaproveitar a mesma lógica de envio de e-mail."""
    if not os.path.exists(CONFIG_FILE):
        return
    try:
        cfg = load_json(CONFIG_FILE, {})
        mapping = {"smtp_user": "SMTP_USER", "smtp_pass": "SMTP_PASS", "smtp_to": "SMTP_TO"}
        for key, env_key in mapping.items():
            if cfg.get(key) and not os.environ.get(env_key):
                os.environ[env_key] = cfg[key]
    except Exception as e:
        print(f"[!] Erro lendo config.json: {e}")


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def parse_price_text(text):
    """Converte '1.234,56' ou '1234.56' em float."""
    if not text:
        return None
    text = text.strip()
    text = re.sub(r"[^\d,\.]", "", text)
    if not text:
        return None
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def detect_site(url):
    if "amazon" in url:
        return "amazon"
    if "mercadolivre" in url or "mercadolibre" in url or "mlb-" in url:
        return "mercadolivre"
    return None


# ---------------------------------------------------------------------------
# Extração por site
# ---------------------------------------------------------------------------

def get_mercadolivre_price(soup):
    el = soup.find("span", class_="andes-money-amount__fraction")
    if el:
        price = el.get_text()
        cents = soup.find("span", class_="andes-money-amount__cents")
        if cents:
            price += "," + cents.get_text()
        return parse_price_text(price)
    return None


def get_amazon_price(soup):
    candidates = [
        ("span", {"id": "priceblock_ourprice"}),
        ("span", {"id": "priceblock_dealprice"}),
        ("span", {"class": "a-price-whole"}),
        ("span", {"class": "a-offscreen"}),
    ]
    for tag, attrs in candidates:
        el = soup.find(tag, attrs)
        if el:
            price = parse_price_text(el.get_text())
            if price:
                return price
    return None


def get_title(soup, site):
    if site == "amazon":
        el = soup.find(id="productTitle")
    else:
        el = soup.find("h1", class_="ui-pdp-title")
    return el.get_text(strip=True) if el else "Produto"


def fetch_price(url):
    site = detect_site(url)
    if not site:
        print(f"  [!] Site não reconhecido: {url}")
        return None, None, None

    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    title = get_title(soup, site)
    price = get_amazon_price(soup) if site == "amazon" else get_mercadolivre_price(soup)
    return site, title, price


# ---------------------------------------------------------------------------
# Comparação com outras lojas ("pesquisa inteligente de preços")
# ---------------------------------------------------------------------------

def simplify_query(title):
    """Reduz o título do produto para uma query de busca mais genérica."""
    words = re.sub(r"[^\w\sÀ-ÿ]", " ", title or "").split()
    return " ".join(words[:6])


def search_mercadolivre(query, limit=3):
    results = []
    try:
        resp = requests.get(
            "https://api.mercadolibre.com/sites/MLB/search",
            params={"q": query, "limit": limit},
            headers=HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        for item in resp.json().get("results", []):
            if item.get("price") is None:
                continue
            results.append({
                "store": "Mercado Livre",
                "title": item.get("title"),
                "price": float(item["price"]),
                "url": item.get("permalink"),
            })
    except Exception as e:
        print(f"    [!] Erro buscando no Mercado Livre: {e}")
    return results


def search_amazon(query, limit=3):
    results = []
    try:
        resp = requests.get(
            "https://www.amazon.com.br/s",
            params={"k": query},
            headers=HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for item in soup.select('div[data-component-type="s-search-result"]')[:limit]:
            title_el = item.select_one("h2 span")
            price_el = item.select_one("span.a-price > span.a-offscreen")
            link_el = item.select_one("h2 a")
            if not (title_el and price_el and link_el):
                continue
            price = parse_price_text(price_el.get_text())
            if price is None:
                continue
            href = link_el.get("href", "")
            url = "https://www.amazon.com.br" + href if href.startswith("/") else href
            results.append({
                "store": "Amazon",
                "title": title_el.get_text(strip=True),
                "price": price,
                "url": url,
            })
    except Exception as e:
        print(f"    [!] Erro buscando na Amazon: {e}")
    return results


def search_magazineluiza(query, limit=3):
    results = []
    try:
        resp = requests.get(
            f"https://www.magazineluiza.com.br/busca/{requests.utils.quote(query)}/",
            headers=HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for item in soup.select('[data-testid="product-card-container"]')[:limit]:
            title_el = item.select_one('[data-testid="product-title"]')
            price_el = item.select_one('[data-testid="price-value"]')
            link_el = item.select_one("a")
            if not (title_el and price_el and link_el):
                continue
            price = parse_price_text(price_el.get_text())
            if price is None:
                continue
            href = link_el.get("href", "")
            url = "https://www.magazineluiza.com.br" + href if href.startswith("/") else href
            results.append({
                "store": "Magazine Luiza",
                "title": title_el.get_text(strip=True),
                "price": price,
                "url": url,
            })
    except Exception as e:
        print(f"    [!] Erro buscando na Magazine Luiza: {e}")
    return results


def search_other_stores(title):
    """Busca o mesmo produto em outras lojas e retorna ofertas ordenadas por preço."""
    query = simplify_query(title)
    if not query:
        return []
    offers = []
    offers += search_mercadolivre(query)
    offers += search_amazon(query)
    offers += search_magazineluiza(query)
    offers.sort(key=lambda o: o["price"])
    return offers


# ---------------------------------------------------------------------------
# E-mail
# ---------------------------------------------------------------------------

def send_email_alert(subject, body):
    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASS")
    smtp_to = os.environ.get("SMTP_TO", smtp_user)

    if not smtp_user or not smtp_pass:
        print("  [i] SMTP não configurado (defina SMTP_USER/SMTP_PASS) — pulando envio de e-mail.")
        return

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = smtp_to

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, [smtp_to], msg.as_string())
    print("  [✓] E-mail de alerta enviado.")


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

def generate_dashboard(history):
    products_json = json.dumps(history, ensure_ascii=False)
    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Monitor de Preços</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
<style>
  :root {{
    --bg: #0f1115;
    --card: #171a21;
    --text: #e8e8ea;
    --muted: #9a9ea6;
    --accent: #34d399;
    --drop: #34d399;
    --rise: #f87171;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    margin: 0;
    padding: 32px 16px 64px;
  }}
  h1 {{
    text-align: center;
    font-weight: 600;
    margin-bottom: 4px;
  }}
  .subtitle {{
    text-align: center;
    color: var(--muted);
    margin-bottom: 32px;
    font-size: 14px;
  }}
  .grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
    gap: 20px;
    max-width: 1100px;
    margin: 0 auto;
  }}
  .card {{
    background: var(--card);
    border-radius: 14px;
    padding: 20px;
    border: 1px solid #262a33;
  }}
  .card h3 {{
    margin: 0 0 4px;
    font-size: 15px;
    font-weight: 600;
    line-height: 1.3;
  }}
  .site-tag {{
    display: inline-block;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--muted);
    margin-bottom: 12px;
  }}
  .price-now {{
    font-size: 28px;
    font-weight: 700;
    color: var(--accent);
  }}
  .price-diff {{
    font-size: 13px;
    margin-left: 8px;
  }}
  .up {{ color: var(--rise); }}
  .down {{ color: var(--drop); }}
  canvas {{ margin-top: 12px; max-height: 140px; }}
  .offers {{ margin-top: 10px; }}
  .offers-title {{
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--muted);
    margin-bottom: 6px;
  }}
  .offer-row {{
    display: flex;
    justify-content: space-between;
    padding: 6px 8px;
    border-radius: 8px;
    font-size: 13px;
    text-decoration: none;
    color: var(--text);
  }}
  .offer-row:hover {{ background: #1e222b; }}
  .offer-row.best {{
    background: rgba(52,211,153,0.1);
    color: var(--accent);
    font-weight: 600;
  }}
  a.link {{
    display: block;
    margin-top: 10px;
    font-size: 12px;
    color: var(--muted);
    text-decoration: none;
  }}
  a.link:hover {{ color: var(--text); }}
  .empty {{
    text-align: center;
    color: var(--muted);
    margin-top: 60px;
  }}
</style>
</head>
<body>
  <h1>📉 Monitor de Preços</h1>
  <div class="subtitle">Atualizado automaticamente • Amazon & Mercado Livre</div>
  <div class="grid" id="grid"></div>
  <div class="empty" id="empty" style="display:none">Nenhum produto monitorado ainda. Adicione links em <code>links.json</code>.</div>

<script>
  const history = {products_json};
  const grid = document.getElementById("grid");
  const urls = Object.keys(history);

  if (urls.length === 0) {{
    document.getElementById("empty").style.display = "block";
  }}

  urls.forEach((url, i) => {{
    const item = history[url];
    const prices = item.prices || [];
    const last = prices[prices.length - 1];
    const prev = prices.length > 1 ? prices[prices.length - 2] : null;

    const card = document.createElement("div");
    card.className = "card";

    let diffHtml = "";
    if (prev && last) {{
      const diff = last.price - prev.price;
      const cls = diff <= 0 ? "down" : "up";
      const arrow = diff <= 0 ? "▼" : "▲";
      diffHtml = `<span class="price-diff ${{cls}}">${{arrow}} R$ ${{Math.abs(diff).toFixed(2)}}</span>`;
    }}

    card.innerHTML = `
      <span class="site-tag">${{item.site || ""}}</span>
      <h3>${{item.title || "Produto"}}</h3>
      <div class="price-now">R$ ${{last ? last.price.toFixed(2) : "-"}} ${{diffHtml}}</div>
      <canvas id="chart-${{i}}"></canvas>
      <div class="offers" id="offers-${{i}}"></div>
      <a class="link" href="${{url}}" target="_blank">Ver produto ↗</a>
    `;
    grid.appendChild(card);

    const offers = item.offers || [];
    const offersEl = document.getElementById(`offers-${{i}}`);
    if (offers.length > 0) {{
      const cheapest = offers[0].price;
      offersEl.innerHTML = '<div class="offers-title">Comparando outras lojas</div>' +
        offers.map(o => {{
          const isBest = o.price === cheapest;
          return `<a class="offer-row ${{isBest ? "best" : ""}}" href="${{o.url}}" target="_blank">
            <span>${{o.store}}${{isBest ? " 🏆" : ""}}</span>
            <span>R$ ${{o.price.toFixed(2)}}</span>
          </a>`;
        }}).join("");
    }}

    if (prices.length > 1) {{
      new Chart(document.getElementById(`chart-${{i}}`), {{
        type: "line",
        data: {{
          labels: prices.map(p => p.date.slice(5, 16)),
          datasets: [{{
            data: prices.map(p => p.price),
            borderColor: "#34d399",
            backgroundColor: "rgba(52,211,153,0.08)",
            fill: true,
            tension: 0.3,
            pointRadius: 2,
          }}]
        }},
        options: {{
          plugins: {{ legend: {{ display: false }} }},
          scales: {{
            x: {{ ticks: {{ color: "#9a9ea6", font: {{ size: 9 }} }}, grid: {{ display: false }} }},
            y: {{ ticks: {{ color: "#9a9ea6", font: {{ size: 9 }} }}, grid: {{ color: "#262a33" }} }},
          }}
        }}
      }});
    }}
  }});
</script>
</body>
</html>
"""
    with open(DASHBOARD_FILE, "w", encoding="utf-8") as f:
        f.write(html)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    load_local_config()
    links = load_json(LINKS_FILE, [])
    history = load_json(HISTORY_FILE, {})
    now = datetime.now().isoformat(timespec="minutes")
    alerts = []

    print(f"Verificando {len(links)} link(s)...")

    for url in links:
        print(f"- {url}")
        try:
            site, title, price = fetch_price(url)
        except Exception as e:
            print(f"  [!] Erro ao buscar: {e}")
            continue

        if price is None:
            print("  [!] Não consegui extrair o preço (site pode ter bloqueado ou mudado o layout).")
            continue

        entry = history.get(url, {"title": title, "site": site, "prices": []})
        prev_price = entry["prices"][-1]["price"] if entry["prices"] else None
        entry["title"] = title
        entry["site"] = site
        entry["prices"].append({"date": now, "price": price})

        print(f"  [✓] {title[:60]} -> R$ {price:.2f}")

        if prev_price is not None and price < prev_price:
            alerts.append(
                f"{title}\n  De R$ {prev_price:.2f} para R$ {price:.2f}\n  {url}"
            )

        # Pesquisa em outras lojas para achar o melhor preço
        print("  [i] Comparando com outras lojas...")
        offers = search_other_stores(title)
        entry["offers"] = offers
        entry["offers_updated"] = now
        history[url] = entry

        if offers:
            best = offers[0]
            print(f"    -> Melhor preço encontrado: {best['store']} R$ {best['price']:.2f}")
            # Só alerta se for uma diferença que valha a pena (mais de 5% mais barato)
            if best["price"] < price * 0.95:
                alerts.append(
                    f"{title}\n  Achei mais barato em {best['store']}: R$ {best['price']:.2f} "
                    f"(seu link está R$ {price:.2f})\n  {best['url']}"
                )

    save_json(HISTORY_FILE, history)
    generate_dashboard(history)

    if alerts:
        body = "Os seguintes produtos baixaram de preço:\n\n" + "\n\n".join(alerts)
        send_email_alert("🔔 Preço baixou!", body)
    else:
        print("Nenhum preço caiu desta vez.")


if __name__ == "__main__":
    main()
    # Quando rodando como .exe (PyInstaller), a janela fecharia sozinha
    # assim que terminasse — segura pra você poder ler o resultado.
    if getattr(sys, "frozen", False):
        input("\nPressione Enter para sair...")
