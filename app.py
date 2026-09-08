import streamlit as st
import pandas as pd
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode, JsCode
import json
import base64
import uuid
import requests
from datetime import date, datetime
from pathlib import Path
from io import BytesIO

# Requer: pip install streamlit-aggrid

st.set_page_config(
    page_title="Retiradas SAO12",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="collapsed",
)

DB_LOCAL = Path("database_retiradas_sao12.json")

STATUS_OPTIONS = [
    "NOVO / SEM CONTATO",
    "CLIENTE AVISADO",
    "AGUARDANDO RETORNO DO CLIENTE",
    "AGUARDANDO AUTORIZAÇÃO",
    "RETIRADA PROGRAMADA",
    "PROCESSO DE ABANDONO",
    "RETIRADO",
    "FINALIZADO",
]

STATUS_FINAL = {"RETIRADO", "FINALIZADO"}

RESPONSAVEIS = [
    "PAULO HENRIQUE",
    "PAULO VASCONCELOS",
    "CLEBER",
    "RENATA",
]

STATUS_MIGRATION = {
    "AGUARDANDO RETIRADA": "NOVO / SEM CONTATO",
    "EM CONTATO COM CLIENTE": "CLIENTE AVISADO",
    "CLIENTE CONTATADO": "CLIENTE AVISADO",
    "AGUARDANDO RETORNO DO CLIENTE": "AGUARDANDO RETORNO DO CLIENTE",
    "AGUARDANDO AUTORIZAÇÃO": "AGUARDANDO AUTORIZAÇÃO",
    "RETIRADA PROGRAMADA": "RETIRADA PROGRAMADA",
    "ABANDONO EM ANDAMENTO": "PROCESSO DE ABANDONO",
    "PROCESSO DE ABANDONO": "PROCESSO DE ABANDONO",
    "RETIRADO": "RETIRADO",
    "DEVOLVIDO / RETORNADO": "FINALIZADO",
    "FINALIZADO": "FINALIZADO",
}

BASE_INICIAL = [
    {"data_chegada": "2026-08-18", "awb": "74547900", "responsavel": "PAULO HENRIQUE", "observacao": "VAI PROVIDENCIAR A AUTORIZAÇÃO DE RETIRADA", "status": "AGUARDANDO AUTORIZAÇÃO"},
    {"data_chegada": "2026-08-26", "awb": "68590082", "responsavel": "PAULO HENRIQUE", "observacao": "", "status": "NOVO / SEM CONTATO"},
    {"data_chegada": "2026-08-27", "awb": "69003513", "responsavel": "RENATA", "observacao": "AGUARDANDO", "status": "AGUARDANDO RETORNO DO CLIENTE"},
    {"data_chegada": "2026-08-31", "awb": "90776770", "responsavel": "RENATA", "observacao": "AGUARDANDO", "status": "AGUARDANDO RETORNO DO CLIENTE"},
    {"data_chegada": "2026-08-31", "awb": "78383723", "responsavel": "RENATA", "observacao": "AGUARDANDO", "status": "AGUARDANDO RETORNO DO CLIENTE"},
    {"data_chegada": "2026-08-31", "awb": "90776394", "responsavel": "CLEBER", "observacao": "", "status": "NOVO / SEM CONTATO"},
    {"data_chegada": "2026-09-02", "awb": "89431064", "responsavel": "RENATA", "observacao": "AGUARDANDO", "status": "AGUARDANDO RETORNO DO CLIENTE"},
    {"data_chegada": "2026-09-02", "awb": "38794011", "responsavel": "RENATA", "observacao": "AGUARDANDO", "status": "AGUARDANDO RETORNO DO CLIENTE"},
    {"data_chegada": "2026-09-03", "awb": "89405341", "responsavel": "RENATA", "observacao": "AGUARDANDO", "status": "AGUARDANDO RETORNO DO CLIENTE"},
    {"data_chegada": "2026-09-03", "awb": "90874243", "responsavel": "RENATA", "observacao": "AGUARDANDO", "status": "AGUARDANDO RETORNO DO CLIENTE"},
    {"data_chegada": "2026-09-03", "awb": "54824980", "responsavel": "RENATA", "observacao": "AGUARDANDO", "status": "AGUARDANDO RETORNO DO CLIENTE"},
    {"data_chegada": "2026-09-04", "awb": "90914751", "responsavel": "RENATA", "observacao": "AGUARDANDO", "status": "AGUARDANDO RETORNO DO CLIENTE"},
    {"data_chegada": "2026-09-04", "awb": "89416386", "responsavel": "RENATA", "observacao": "AGUARDANDO", "status": "AGUARDANDO RETORNO DO CLIENTE"},
]


def now_iso():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today_iso():
    return date.today().isoformat()


def clean_awb(value):
    txt = str(value or "").strip()
    if txt.endswith(".0"):
        txt = txt[:-2]
    return txt


def br_date(value):
    if not value:
        return ""
    try:
        return datetime.fromisoformat(str(value)[:10]).strftime("%d/%m/%Y")
    except Exception:
        return str(value)


def get_github_config():
    try:
        token = st.secrets.get("GITHUB_TOKEN", "")
        repo = st.secrets.get("GITHUB_REPO", "")
        branch = st.secrets.get("GITHUB_DATA_BRANCH", "main")
        path = st.secrets.get("GITHUB_RETIRADAS_DB_PATH", "database_retiradas_sao12.json")
        if token and repo:
            return token, repo, branch, path
    except Exception:
        pass
    return None


def github_headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def load_db():
    cfg = get_github_config()
    if cfg:
        token, repo, branch, path = cfg
        url = f"https://api.github.com/repos/{repo}/contents/{path}"
        try:
            r = requests.get(url, headers=github_headers(token), params={"ref": branch}, timeout=20)
            if r.status_code == 200:
                payload = r.json()
                content = base64.b64decode(payload["content"]).decode("utf-8")
                data = json.loads(content)
                data.setdefault("registros", [])
                return data
            if r.status_code == 404:
                return {"registros": []}
        except Exception:
            pass

    if DB_LOCAL.exists():
        try:
            data = json.loads(DB_LOCAL.read_text(encoding="utf-8"))
            data.setdefault("registros", [])
            return data
        except Exception:
            pass

    return {"registros": []}


def save_db(data):
    data["ultima_atualizacao"] = now_iso()

    try:
        DB_LOCAL.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass

    cfg = get_github_config()
    if not cfg:
        return True, "Dados salvos."

    token, repo, branch, path = cfg
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    headers = github_headers(token)

    try:
        sha = None
        current = requests.get(url, headers=headers, params={"ref": branch}, timeout=20)

        if current.status_code == 200:
            sha = current.json().get("sha")
        elif current.status_code != 404:
            current.raise_for_status()

        payload = {
            "message": f"Atualização automática Retiradas SAO12 - {now_iso()}",
            "content": base64.b64encode(
                json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
            ).decode("ascii"),
            "branch": branch,
        }
        if sha:
            payload["sha"] = sha

        r = requests.put(url, headers=headers, json=payload, timeout=20)
        r.raise_for_status()
        return True, "Dados salvos no banco permanente."
    except Exception as exc:
        return False, f"Salvo localmente, mas o banco permanente não foi atualizado: {exc}"


def history_add(reg, action, details=""):
    reg.setdefault("historico", []).append(
        {"data_hora": now_iso(), "acao": action, "detalhes": details}
    )


def ensure_fields(reg):
    if "observacao" not in reg:
        reg["observacao"] = reg.get("resposta_cliente", "")

    old_status = str(reg.get("status", "NOVO / SEM CONTATO")).strip().upper()
    reg["status"] = STATUS_MIGRATION.get(old_status, reg.get("status", "NOVO / SEM CONTATO"))

    if not reg.get("data_ultimo_status"):
        origem = str(reg.get("atualizado_em", ""))[:10]
        if len(origem) != 10:
            origem = str(reg.get("data_chegada", ""))[:10]
        reg["data_ultimo_status"] = origem

    defaults = {
        "telefone_remetente": "",
        "telefone_unidade_origem": "",
        "email_remetente": "",
        "email_destinatario": "",
        "email_base_origem": "",
        "responsavel": "",
        "observacao": "",
        "status": "NOVO / SEM CONTATO",
        "data_ultimo_status": str(reg.get("data_chegada", ""))[:10],
        "data_prevista_retirada": "",
        "data_finalizacao": "",
        "criado_em": now_iso(),
        "atualizado_em": now_iso(),
        "historico": [],
    }
    for key, value in defaults.items():
        reg.setdefault(key, value)


def make_base_record(item):
    return {
        "id": str(uuid.uuid4()),
        "data_chegada": item["data_chegada"],
        "awb": item["awb"],
        "telefone_remetente": "",
        "telefone_unidade_origem": "",
        "email_remetente": "",
        "email_destinatario": "",
        "email_base_origem": "",
        "responsavel": item.get("responsavel", ""),
        "observacao": item.get("observacao", ""),
        "status": item.get("status", "NOVO / SEM CONTATO"),
        "data_ultimo_status": item["data_chegada"],
        "data_prevista_retirada": "",
        "data_finalizacao": "",
        "criado_em": now_iso(),
        "atualizado_em": now_iso(),
        "historico": [{"data_hora": now_iso(), "acao": "Carga trazida da planilha base", "detalhes": ""}],
    }


def days_stopped(reg):
    try:
        inicio = datetime.fromisoformat(str(reg.get("data_chegada"))[:10]).date()
        if reg.get("status") in STATUS_FINAL and reg.get("data_finalizacao"):
            fim = datetime.fromisoformat(str(reg.get("data_finalizacao"))[:10]).date()
        else:
            fim = date.today()
        return max((fim - inicio).days, 0)
    except Exception:
        return 0


def prazo_bucket(reg):
    dias = days_stopped(reg)
    if dias >= 20:
        return "20+"
    if dias >= 15:
        return "15-19"
    if dias >= 3:
        return "3-14"
    return "0-2"


def prazo_label(reg):
    bucket = prazo_bucket(reg)
    if bucket == "20+":
        return "🚨 20+ DIAS"
    if bucket == "15-19":
        return "🔴 15–19 DIAS"
    if bucket == "3-14":
        return "🟠 3–14 DIAS"
    return "🟢 0–2 DIAS"


def row_colors(reg):
    bucket = prazo_bucket(reg)
    if bucket == "20+":
        return "#f2b8b8", "#7f0000"
    if bucket == "15-19":
        return "#fde0e0", "#8b1a1a"
    if bucket == "3-14":
        return "#fff0c2", "#6f5200"
    return "#def3e4", "#165c2b"


def export_excel(registros):
    rows = []
    for r in registros:
        rows.append({
            "Prazo": prazo_label(r),
            "Dias": days_stopped(r),
            "Data chegada": br_date(r.get("data_chegada")),
            "AWB": r.get("awb", ""),
            "Status": r.get("status", ""),
            "Data último status": br_date(r.get("data_ultimo_status")),
            "Data prevista retirada": br_date(r.get("data_prevista_retirada")),
            "Responsável": r.get("responsavel", ""),
            "Observação": r.get("observacao", ""),
            "Telefone remetente": r.get("telefone_remetente", ""),
            "Telefone unidade origem": r.get("telefone_unidade_origem", ""),
            "E-mail remetente": r.get("email_remetente", ""),
            "E-mail destinatário": r.get("email_destinatario", ""),
            "E-mail base origem": r.get("email_base_origem", ""),
            "Data finalização": br_date(r.get("data_finalizacao")),
            "Dias totais parada": days_stopped(r),
            "Última atualização": r.get("atualizado_em", ""),
        })

    df = pd.DataFrame(rows)
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="RETIRADAS", index=False)
    return output.getvalue()



def find_reg(rid):
    return next(
        (
            r for r in st.session_state.db.get("registros", [])
            if str(r.get("id")) == str(rid)
        ),
        None,
    )


# ---------------- INICIALIZAÇÃO ----------------

if "db" not in st.session_state:
    st.session_state.db = load_db()

db = st.session_state.db
registros = db["registros"]

for reg in registros:
    ensure_fields(reg)

if not registros:
    registros.extend(make_base_record(item) for item in BASE_INICIAL)
    save_db(db)
else:
    save_db(db)

if "mostrar_form_nova" not in st.session_state:
    st.session_state.mostrar_form_nova = False

if "filtro_card" not in st.session_state:
    st.session_state.filtro_card = ""

if "pending_final" not in st.session_state:
    st.session_state.pending_final = None


# ---------------- CSS ----------------

st.markdown("""
<style>
[data-testid="stSidebar"] {display:none;}

.block-container {
    padding-top: 1.8rem;
    padding-bottom: 3rem;
    max-width: 1650px;
}

div.stButton > button {
    border-radius: 10px;
    font-weight: 700;
    text-align: center !important;
    justify-content: center !important;
}

.st-key-top_actions button {
    min-height: 42px !important;
}
.st-key-top_actions button p {
    text-align: center !important;
    width: 100% !important;
}

/* CARDS */
.st-key-cards button {
    min-height: 92px !important;
    font-weight: 900 !important;
    font-size: 15px !important;
    text-align: center !important;
    justify-content: center !important;
}
.st-key-cards button p {
    text-align: center !important;
    width: 100% !important;
    font-weight: 900 !important;
}

/* Ordem solicitada: vermelho, amarelo, verde, vermelho */
.st-key-cards div[data-testid="column"]:nth-child(1) button {
    background:#fde0e0 !important;
    border:1px solid #ef9a9a !important;
    color:#8b1a1a !important;
}
.st-key-cards div[data-testid="column"]:nth-child(2) button {
    background:#fff0c2 !important;
    border:1px solid #f2ce67 !important;
    color:#6f5200 !important;
}
.st-key-cards div[data-testid="column"]:nth-child(3) button {
    background:#def3e4 !important;
    border:1px solid #9bd2aa !important;
    color:#165c2b !important;
}
.st-key-cards div[data-testid="column"]:nth-child(4) button {
    background:#f2b8b8 !important;
    border:1px solid #df6f6f !important;
    color:#7f0000 !important;
}

/* AGGRID */
.ag-theme-streamlit {
    --ag-row-border-style: solid;
    --ag-row-border-width: 1px;
    --ag-row-border-color: rgba(0,0,0,.08);
    --ag-header-background-color: #eef1f5;
    --ag-header-foreground-color: #1f2630;
    --ag-font-size: 12px;
}
</style>
""", unsafe_allow_html=True)


st.title("📦 RETIRADAS SAO12")
st.caption("Cadastro e acompanhamento das cargas aguardando retirada.")

with st.container(key="top_actions"):
    b1, b2, spacer = st.columns([1.2, 1.4, 4])

    if b1.button(
        "➕ ADICIONAR NOVA CARGA",
        use_container_width=True,
        type="primary" if st.session_state.mostrar_form_nova else "secondary",
    ):
        st.session_state.mostrar_form_nova = not st.session_state.mostrar_form_nova
        st.rerun()

    if b2.button("📋 ACOMPANHAR RETIRADAS", use_container_width=True):
        st.session_state.mostrar_form_nova = False
        st.rerun()


# ---------------- NOVA CARGA ----------------

if st.session_state.mostrar_form_nova:
    st.divider()
    st.subheader("Adicionar nova carga")

    with st.form("nova_carga", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)

        data_chegada = c1.date_input(
            "Data que a carga chegou *",
            value=date.today(),
            format="DD/MM/YYYY",
        )
        awb = c2.text_input("AWB *")
        responsavel = c3.selectbox(
            "Responsável",
            [""] + RESPONSAVEIS,
            index=0,
        )

        c1, c2 = st.columns(2)
        telefone_rem = c1.text_input("Telefone remetente")
        telefone_origem = c2.text_input("Telefone unidade origem")

        c1, c2, c3 = st.columns(3)
        email_rem = c1.text_input("E-mail remetente")
        email_dest = c2.text_input("E-mail destinatário")
        email_origem = c3.text_input("E-mail base origem")

        observacao = st.text_area("Observação inicial")

        salvar = st.form_submit_button(
            "SALVAR NOVA CARGA",
            type="primary",
            use_container_width=True,
        )

    if salvar:
        awb = clean_awb(awb)

        if not awb:
            st.error("Informe a AWB.")
        elif any(
            clean_awb(r.get("awb")) == awb
            and r.get("status") not in STATUS_FINAL
            for r in registros
        ):
            st.error("Já existe uma carga em aberto com essa AWB.")
        else:
            reg = {
                "id": str(uuid.uuid4()),
                "data_chegada": data_chegada.isoformat(),
                "awb": awb,
                "telefone_remetente": telefone_rem.strip(),
                "telefone_unidade_origem": telefone_origem.strip(),
                "email_remetente": email_rem.strip(),
                "email_destinatario": email_dest.strip(),
                "email_base_origem": email_origem.strip(),
                "responsavel": responsavel.strip(),
                "observacao": observacao.strip(),
                "status": "NOVO / SEM CONTATO",
                "data_ultimo_status": today_iso(),
                "data_prevista_retirada": "",
                "data_finalizacao": "",
                "criado_em": now_iso(),
                "atualizado_em": now_iso(),
                "historico": [],
            }
            history_add(reg, "Nova carga cadastrada")
            registros.append(reg)
            save_db(db)

            st.session_state.mostrar_form_nova = False
            st.success(f"AWB {awb} cadastrada.")
            st.rerun()


st.divider()


# ---------------- CARDS ----------------

ativos = [r for r in registros if r.get("status") not in STATUS_FINAL]
qtd_3_14 = sum(prazo_bucket(r) == "3-14" for r in ativos)
qtd_15_19 = sum(prazo_bucket(r) == "15-19" for r in ativos)
qtd_20 = sum(prazo_bucket(r) == "20+" for r in ativos)

with st.container(key="cards"):
    c1, c2, c3, c4 = st.columns(4)

    if c1.button(f"CARGAS EM ABERTO\n\n{len(ativos)}", use_container_width=True, key="card_abertos"):
        st.session_state.filtro_card = "" if st.session_state.filtro_card == "todos" else "todos"
        st.rerun()

    if c2.button(f"3–14 DIAS\n\n{qtd_3_14}", use_container_width=True, key="card_3_14"):
        st.session_state.filtro_card = "" if st.session_state.filtro_card == "3-14" else "3-14"
        st.rerun()

    if c3.button(f"15–19 DIAS\n\n{qtd_15_19}", use_container_width=True, key="card_15_19"):
        st.session_state.filtro_card = "" if st.session_state.filtro_card == "15-19" else "15-19"
        st.rerun()

    if c4.button(f"20+ DIAS\n\n{qtd_20}", use_container_width=True, key="card_20"):
        st.session_state.filtro_card = "" if st.session_state.filtro_card == "20+" else "20+"
        st.rerun()

if st.session_state.filtro_card:
    if st.session_state.filtro_card == "todos":
        lista = ativos
        titulo = "Cargas em aberto"
    else:
        lista = [r for r in ativos if prazo_bucket(r) == st.session_state.filtro_card]
        titulo = f"Cargas na faixa {st.session_state.filtro_card} dias"

    lista = sorted(lista, key=lambda r: days_stopped(r), reverse=True)

    if lista:
        texto = " • ".join(f"{r.get('awb')} ({days_stopped(r)} dias)" for r in lista)
        st.info(f"**{titulo}:** {texto}")
    else:
        st.info("Nenhuma carga nessa faixa.")


# ---------------- ACOMPANHAMENTO ----------------

st.subheader("Acompanhamento")
st.caption(
    "Edite diretamente **Status**, **Responsável**, **Observação** e, quando houver, "
    "**Prev. retirada**. Depois clique em **💾 SALVAR ALTERAÇÕES**."
)

busca = st.text_input("🔎 Buscar AWB", placeholder="Digite uma AWB...").strip()

visiveis = ativos
if busca:
    visiveis = [
        r for r in visiveis
        if busca.lower() in str(r.get("awb", "")).lower()
    ]

visiveis = sorted(
    visiveis,
    key=lambda r: (days_stopped(r), r.get("data_chegada", "")),
    reverse=True,
)

if st.session_state.get("toast_msg"):
    st.toast(st.session_state.pop("toast_msg"), icon="✅")

if not visiveis:
    st.info("Nenhuma carga em aberto encontrada.")
else:
    df_grid = pd.DataFrame([
        {
            "_id": r["id"],
            "Prazo": prazo_label(r),
            "Dias": days_stopped(r),
            "Data chegada": br_date(r.get("data_chegada")),
            "AWB": r.get("awb", ""),
            "Status": r.get("status", ""),
            "Data último status": br_date(r.get("data_ultimo_status")),
            "Prev. retirada": br_date(r.get("data_prevista_retirada")),
            "Responsável": r.get("responsavel", ""),
            "Observação": r.get("observacao", ""),
        }
        for r in visiveis
    ])

    row_style = JsCode("""
    function(params) {
        const dias = Number(params.data.Dias || 0);
        if (dias >= 20) {
            return {'backgroundColor': '#f2b8b8', 'color': '#7f0000', 'fontWeight': '600'};
        } else if (dias >= 15) {
            return {'backgroundColor': '#fde0e0', 'color': '#8b1a1a', 'fontWeight': '600'};
        } else if (dias >= 3) {
            return {'backgroundColor': '#fff0c2', 'color': '#6f5200', 'fontWeight': '600'};
        } else {
            return {'backgroundColor': '#def3e4', 'color': '#165c2b', 'fontWeight': '600'};
        }
    }
    """)

    gb = GridOptionsBuilder.from_dataframe(df_grid)

    # Colunas bloqueadas
    for col in ["_id", "Prazo", "Dias", "Data chegada", "AWB", "Data último status"]:
        gb.configure_column(col, editable=False)

    gb.configure_column("_id", hide=True)

    gb.configure_column(
        "Prazo",
        header_name="PRAZO",
        minWidth=115,
        maxWidth=125,
        cellStyle={"textAlign": "center"},
        headerClass="ag-center-aligned-header",
    )
    gb.configure_column(
        "Dias",
        header_name="DIAS",
        minWidth=65,
        maxWidth=75,
        cellStyle={"textAlign": "center"},
        headerClass="ag-center-aligned-header",
    )
    gb.configure_column(
        "Data chegada",
        header_name="DATA CHEGADA",
        minWidth=105,
        maxWidth=115,
        cellStyle={"textAlign": "center"},
        headerClass="ag-center-aligned-header",
    )
    gb.configure_column(
        "AWB",
        header_name="AWB",
        minWidth=105,
        maxWidth=115,
        cellStyle={"textAlign": "center", "fontWeight": "700"},
        headerClass="ag-center-aligned-header",
    )

    gb.configure_column(
        "Status",
        header_name="STATUS",
        editable=True,
        cellEditor="agSelectCellEditor",
        cellEditorParams={"values": STATUS_OPTIONS},
        minWidth=225,
        flex=1.35,
        headerClass="ag-center-aligned-header",
    )

    gb.configure_column(
        "Data último status",
        header_name="DATA ÚLTIMO STATUS",
        minWidth=135,
        maxWidth=145,
        cellStyle={"textAlign": "center"},
        headerClass="ag-center-aligned-header",
    )

    gb.configure_column(
        "Prev. retirada",
        header_name="PREV. RETIRADA",
        editable=True,
        minWidth=120,
        maxWidth=130,
        cellStyle={"textAlign": "center"},
        headerClass="ag-center-aligned-header",
    )

    gb.configure_column(
        "Responsável",
        header_name="RESPONSÁVEL",
        editable=True,
        cellEditor="agSelectCellEditor",
        cellEditorParams={"values": RESPONSAVEIS},
        minWidth=165,
        maxWidth=180,
        headerClass="ag-center-aligned-header",
    )

    gb.configure_column(
        "Observação",
        header_name="OBSERVAÇÃO",
        editable=True,
        minWidth=320,
        flex=2.2,
        headerClass="ag-center-aligned-header",
    )

    gb.configure_grid_options(
        getRowStyle=row_style,
        rowHeight=38,
        headerHeight=36,
        suppressRowClickSelection=True,
        stopEditingWhenCellsLoseFocus=True,
        singleClickEdit=True,
        ensureDomOrder=True,
    )

    grid_options = gb.build()

    grid_response = AgGrid(
        df_grid,
        gridOptions=grid_options,
        update_mode=GridUpdateMode.VALUE_CHANGED,
        data_return_mode=DataReturnMode.AS_INPUT,
        fit_columns_on_grid_load=False,
        allow_unsafe_jscode=True,
        theme="streamlit",
        height=min(620, 42 + (len(df_grid) * 38)),
        key="aggrid_retiradas",
        reload_data=False,
    )

    # IMPORTANTE:
    # O AgGrid mantém as alterações no navegador. Para garantir persistência,
    # esta versão possui um botão explícito que grava TODA a tabela no banco.
    edited = pd.DataFrame(grid_response["data"])

    st.caption("Após editar a tabela, clique em **💾 SALVAR ALTERAÇÕES** para gravar permanentemente.")

    if st.button(
        "💾 SALVAR ALTERAÇÕES",
        type="primary",
        use_container_width=True,
        key="salvar_tabela"
    ):
        changed_any = False
        erros = []
        pending_final = None
        by_id = {str(r["id"]): r for r in visiveis}

        for _, row in edited.iterrows():
            rid = str(row.get("_id", ""))
            reg = by_id.get(rid)
            if not reg:
                continue

            new_status = str(row.get("Status", "") or "").strip()
            new_resp = str(row.get("Responsável", "") or "").strip()
            new_obs = str(row.get("Observação", "") or "").strip()
            new_prev = str(row.get("Prev. retirada", "") or "").strip()

            old_status = str(reg.get("status", "") or "")
            old_resp = str(reg.get("responsavel", "") or "")
            old_obs = str(reg.get("observacao", "") or "")
            old_prev_iso = str(reg.get("data_prevista_retirada", "") or "")
            old_prev_br = br_date(old_prev_iso)

            # Se encerrar, guarda para confirmação antes de retirar do acompanhamento.
            if new_status in STATUS_FINAL and old_status not in STATUS_FINAL:
                pending_final = {
                    "id": rid,
                    "awb": reg.get("awb", ""),
                    "novo_status": new_status,
                    "status_anterior": old_status,
                    "responsavel": new_resp,
                    "observacao": new_obs,
                    "prev_retirada": new_prev,
                }
                continue

            details = []

            if new_status != old_status:
                reg["status"] = new_status
                reg["data_ultimo_status"] = today_iso()
                details.append(f"Status: {old_status} → {new_status}")

                if new_status != "RETIRADA PROGRAMADA":
                    reg["data_prevista_retirada"] = ""

            if new_resp != old_resp:
                reg["responsavel"] = new_resp
                details.append(f"Responsável: {old_resp or '-'} → {new_resp or '-'}")

            if new_obs != old_obs:
                reg["observacao"] = new_obs
                details.append(
                    f"Observação anterior: {old_obs or '-'} | Nova: {new_obs or '-'}"
                )

            # Previsão de retirada somente quando o status for RETIRADA PROGRAMADA.
            if new_status == "RETIRADA PROGRAMADA":
                new_prev_iso = ""
                if new_prev:
                    try:
                        new_prev_iso = datetime.strptime(
                            new_prev, "%d/%m/%Y"
                        ).date().isoformat()
                    except Exception:
                        erros.append(
                            f"AWB {reg.get('awb','')}: data de previsão inválida. Use DD/MM/AAAA."
                        )
                        new_prev_iso = old_prev_iso

                if new_prev_iso != old_prev_iso:
                    reg["data_prevista_retirada"] = new_prev_iso
                    details.append(
                        f"Previsão retirada: {old_prev_br or '-'} → "
                        f"{br_date(new_prev_iso) or '-'}"
                    )

            if details:
                reg["atualizado_em"] = now_iso()
                history_add(
                    reg,
                    "Alteração salva na tabela",
                    "; ".join(details)
                )
                changed_any = True

        # Salva o banco UMA VEZ após processar todas as linhas.
        if changed_any:
            ok, msg = save_db(db)
            if ok:
                st.success("✅ ALTERAÇÕES SALVAS COM SUCESSO.")
            else:
                st.error(
                    "⚠️ As alterações foram salvas apenas localmente. "
                    "O banco permanente não foi atualizado."
                )
                st.warning(msg)
        elif not pending_final and not erros:
            st.info("Nenhuma alteração nova para salvar.")

        for erro in erros:
            st.warning(erro)

        if pending_final:
            st.session_state.pending_final = pending_final
            # Salva outras mudanças antes da confirmação do encerramento.
            if changed_any:
                save_db(db)
            st.rerun()


# ---------------- CONFIRMAÇÃO FINAL ----------------

if st.session_state.pending_final:
    p = st.session_state.pending_final

    st.warning(
        f"⚠️ Confirmar encerramento da AWB **{p['awb']}** como "
        f"**{p['novo_status']}**? Após confirmar, ela sairá do acompanhamento."
    )

    c1, c2, spacer = st.columns([1, 1, 3])

    if c1.button("CONFIRMAR ENCERRAMENTO", type="primary", use_container_width=True):
        reg = find_reg(p["id"])

        if not reg:
            st.error("Não foi possível localizar esta AWB no banco de dados.")
        else:
            old_status = reg.get("status", "")
            reg["status"] = p["novo_status"]
            reg["responsavel"] = p.get("responsavel", reg.get("responsavel", ""))
            reg["observacao"] = p.get("observacao", reg.get("observacao", ""))
            reg["data_ultimo_status"] = today_iso()
            reg["data_finalizacao"] = today_iso()
            reg["atualizado_em"] = now_iso()

            history_add(
                reg,
                "Carga encerrada",
                f"Status: {old_status} → {p['novo_status']}",
            )

            ok, msg = save_db(db)

            if ok:
                st.session_state.pending_final = None
                st.session_state["toast_msg"] = (
                    f"AWB {reg.get('awb','')} encerrada e removida do acompanhamento."
                )
                st.rerun()
            else:
                st.error(
                    "A carga foi alterada localmente, mas não consegui salvar "
                    "o encerramento no banco permanente."
                )
                st.warning(msg)

    if c2.button("CANCELAR", use_container_width=True):
        st.session_state.pending_final = None
        st.rerun()


st.divider()


# ---------------- RELATÓRIO ----------------

with st.expander("📥 Exportar relatório completo"):
    st.caption("Inclui cargas em acompanhamento e também todas as cargas já retiradas/finalizadas.")

    excel = export_excel(registros)

    st.download_button(
        "BAIXAR RELATÓRIO EM EXCEL",
        data=excel,
        file_name=f"retiradas_sao12_{date.today().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )


if get_github_config():
    st.caption("🟢 Banco permanente conectado.")
else:
    st.caption(
        "🖥️ Teste no PC: os dados ficam salvos no arquivo "
        "database_retiradas_sao12.json na mesma pasta do app."
    )
