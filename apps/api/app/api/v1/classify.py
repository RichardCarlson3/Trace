from fastapi import APIRouter, Request

from app.schemas.contracts import Classification, ClassifyRequest

router = APIRouter()


@router.post(
    "/classify",
    response_model=Classification,
    tags=["classification"],
    summary="Classify a citation-context passage",
    description=(
        "Returns an intent and its uncalibrated predict_proba score from the locally "
        "trained SciCite pipeline. The model version comes from the verified artifact metadata."
    ),
    responses={
        503: {"description": "Model artifacts are missing or incompatible"},
        500: {"description": "Unexpected inference failure"},
    },
)
def classify(body: ClassifyRequest, request: Request):
    return request.app.state.inference.classify(body.context_text)
