import os
import json
from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["Missions"])

MISSIONS_DIR = "data/missions"

@router.get("/missions")
async def list_missions(namespace: str = "global"):
    """Lista todas as missões concluídas em um namespace."""
    ns_dir = os.path.join(MISSIONS_DIR, namespace)
    if not os.path.exists(ns_dir):
        return {"missions": []}
        
    missions = []
    for filename in os.listdir(ns_dir):
        if filename.endswith(".json"):
            path = os.path.join(ns_dir, filename)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Retorna um resumo para a lista
                    missions.append({
                        "id": data.get("id"),
                        "mission": data.get("mission"),
                        "timestamp": data.get("timestamp")
                    })
            except Exception:
                continue
                
    # Ordena por timestamp mais recente
    missions.sort(key=lambda x: x["timestamp"], reverse=True)
    return {"missions": missions}

@router.get("/missions/{mission_id}")
async def get_mission_report(mission_id: str, namespace: str = "global"):
    """Retorna o relatório completo de uma missão."""
    path = os.path.join(MISSIONS_DIR, namespace, f"{mission_id}.json")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Relatório não encontrado")
        
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
