from .access import AccessControl
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from .core import ProfileRequest, analyze

app = FastAPI(title="DataPilot", version="0.4.0")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def index():
    return Path(__file__).with_name("index.html").read_text()


@app.post("/analyze")
def run(request: ProfileRequest):
    return analyze(request)


from .guard import InputGuard

app.add_middleware(InputGuard)


app.mount(
    "/assets", StaticFiles(directory=Path(__file__).with_name("static")), name="assets"
)


@app.get("/guide", response_class=PlainTextResponse)
def user_guide():
    return Path(__file__).with_name("USER_GUIDE.md").read_text()


from .contracts import ContractRequest, validate_contract


@app.post("/contracts/validate")
def validate_table_contract(request: ContractRequest):
    return validate_contract(request)


app.add_middleware(AccessControl)
