from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, HttpUrl
from typing import Optional

from . import api

app = FastAPI(title="StreamDoctor API")


class AnalyzeRequest(BaseModel):
    url: str = Field(..., description="RTMP/RTSP stream URL")
    duration: int = Field(30, gt=0, le=600, description="Analysis duration in seconds")


class RemediateRequest(AnalyzeRequest):
    pass


@app.get("/health")
def health():
    return {"status": "ok", "service": "streamdoctor"}


@app.post("/analyze")
def analyze(req: AnalyzeRequest):
    if not req.url:
        raise HTTPException(status_code=400, detail={"error": "invalid_request", "message": "url is required"})

    try:
        res = api.analyze_stream(req.url, duration=req.duration)
        return res.to_dict()
    except api.StreamDoctorAPIError as exc:
        raise HTTPException(status_code=502, detail={"error": "analysis_failed", "message": str(exc)})
    except Exception as exc:
        raise HTTPException(status_code=502, detail={"error": "analysis_failed", "message": "Unexpected analysis error"})


@app.post("/diagnose")
def diagnose(req: AnalyzeRequest):
    if not req.url:
        raise HTTPException(status_code=400, detail={"error": "invalid_request", "message": "url is required"})

    try:
        res = api.analyze_and_diagnose(req.url, duration=req.duration)
        return res.to_dict()
    except api.StreamDoctorAPIError as exc:
        raise HTTPException(status_code=502, detail={"error": "diagnosis_failed", "message": str(exc)})
    except Exception:
        raise HTTPException(status_code=500, detail={"error": "internal_error", "message": "Unexpected error"})


@app.post("/remediate")
def remediate(req: RemediateRequest):
    if not req.url:
        raise HTTPException(status_code=400, detail={"error": "invalid_request", "message": "url is required"})

    try:
        # v1 is dry-run only: recommendations without execution
        res = api.plan_remediation(req.url, duration=req.duration)
        return res.to_dict()
    except api.StreamDoctorAPIError as exc:
        raise HTTPException(status_code=502, detail={"error": "remediation_failed", "message": str(exc)})
    except Exception:
        raise HTTPException(status_code=500, detail={"error": "internal_error", "message": "Unexpected error"})
