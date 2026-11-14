from fastapi import APIRouter, Request

from app.schemas.contracts import Classification, ClassifyRequest

router = APIRouter()


@router.post("/classify", response_model=Classification, tags=["classification"])
def classify(body: ClassifyRequest, request: Request):
    return request.app.state.inference.classify(body.context_text)
