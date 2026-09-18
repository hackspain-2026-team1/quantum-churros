from contextlib import asynccontextmanager
import json
from uuid import uuid4

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, SQLModel, create_engine, select

from xray_engine.demo import demo_overview

from .config import settings
from .models import ActionUpdate, Entity, RecommendedAction, ScenarioProjection, ScenarioRecord, ScenarioRequest, ScenarioResponse, Workspace

engine = create_engine(settings.database_url, pool_pre_ping=True)


@asynccontextmanager
async def lifespan(_: FastAPI):
    with Session(engine) as session:
        if session.get(Workspace, "WORKSPACE_DEMO") is None:
            session.add(Workspace(id="WORKSPACE_DEMO", name="Embat X-Ray Demo"))
            session.add(Entity(id="GROUP_0042", workspace_id="WORKSPACE_DEMO", name="Grupo Velasco", kind="group"))
            session.add(Entity(id="COMP_0680", workspace_id="WORKSPACE_DEMO", parent_id="GROUP_0042", name="Velasco Industrial", kind="company"))
        seeds = [
            RecommendedAction(id="collect-overdue", entity_id="COMP_0680", title="Priorizar el cobro de cinco facturas", owner="Tesorería", status="in_progress", expected_impact="+4–6 puntos"),
            RecommendedAction(id="refinance-line", entity_id="COMP_0680", title="Renegociar la línea de circulante", owner="CFO", status="pending", expected_impact="+180 k€ de margen"),
            RecommendedAction(id="monitor-volatility", entity_id="COMP_0680", title="Vigilar la volatilidad de caja", owner="Analista", status="in_progress", expected_impact="Revisar en el próximo cierre"),
        ]
        for action in seeds:
            if session.get(RecommendedAction, action.id) is None:
                session.add(action)
        session.commit()
    yield


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins.split(","), allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/demo")
def get_demo() -> dict[str, object]:
    overview = demo_overview()
    with Session(engine) as session:
        stored = {action.id: action.status for action in session.exec(select(RecommendedAction))}
    labels = {"pending": "Por iniciar", "in_progress": "En curso", "resolved": "Resuelta", "reopened": "Reabierta"}
    for action in overview["actions"]:
        action["status"] = labels.get(stored.get(action["id"], "pending"), stored.get(action["id"], "Por iniciar"))
    return overview


@app.get("/api/v1/actions", response_model=list[RecommendedAction])
def get_actions() -> list[RecommendedAction]:
    with Session(engine) as session:
        return list(session.exec(select(RecommendedAction)))


@app.patch("/api/v1/actions/{action_id}", response_model=RecommendedAction)
def update_action(action_id: str, update: ActionUpdate) -> RecommendedAction:
    with Session(engine) as session:
        action = session.get(RecommendedAction, action_id)
        if action is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Action not found")
        action.status = update.status
        session.add(action)
        session.commit()
        session.refresh(action)
        return action


@app.post("/api/v1/scenarios", response_model=ScenarioResponse)
def calculate_scenario(request: ScenarioRequest) -> ScenarioResponse:
    improvement = min(18, request.collection_days * 0.22 + request.refinance_amount / 60_000 + request.payment_extension_days * 0.12)
    projected = round(68 + improvement, 1)
    scenario_id = f"SCN_{uuid4().hex[:12]}" if request.persist else "preview"
    low = max(0, projected - 3.5)
    high = min(100, projected + 2.5)
    if request.persist:
        with Session(engine) as session:
            session.add(ScenarioRecord(id=scenario_id, entity_id="COMP_0680", base_score=68, assumptions_json=json.dumps(request.model_dump()), status="calculated"))
            for offset, score in enumerate((70.0, 72.0, 74.0, projected), start=1):
                session.add(ScenarioProjection(id=f"{scenario_id}_{offset}", scenario_id=scenario_id, month_offset=offset, score=score, confidence_low=max(0, score - 3.5), confidence_high=min(100, score + 2.5)))
            session.commit()
    return ScenarioResponse(scenario_id=scenario_id, status="calculated" if request.persist else "preview", base_score=68, projected_score=projected, projected_cash=int(request.refinance_amount + request.collection_days * 2_800 + request.payment_extension_days * 1_500), confidence_low=low, confidence_high=high)
