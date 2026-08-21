from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field
from providers.schemas import TaskType

class AudioReferencePayload(BaseModel):
    storageProvider: str
    bucket: str
    objectKey: str
    checksumSha256: str
    contentType: str
    durationSeconds: float

class SpeakingEvaluationRequestedPayload(BaseModel):
    attemptId: UUID
    studentId: UUID
    part: str = "PART_1"
    audioRef: AudioReferencePayload

class WritingEvaluationRequestedPayload(BaseModel):
    submissionId: UUID
    studentId: UUID
    taskType: TaskType
    taskPrompt: str
    essayText: str
    wordCount: int

class SpeakingEvaluationCompletedPayload(BaseModel):
    attemptId: UUID
    fluencyCoherenceScore: float
    lexicalResourceScore: float
    grammaticalRangeScore: float
    pronunciationScore: float
    overallBand: float
    feedbackDetail: Dict[str, Any]

class SpeakingEvaluationFailedPayload(BaseModel):
    attemptId: UUID
    errorCode: str
    errorMessage: str
    isRetriable: bool
    failedAt: datetime

class EventEnvelope(BaseModel):
    eventId: UUID
    idempotencyKey: UUID
    eventType: str
    schemaVersion: str = "1.0"
    occurredAt: datetime
    producedAt: datetime
    traceId: Optional[str] = None
    correlationId: Optional[str] = None
    source: str
    retryCount: int = 0
    payload: WritingEvaluationRequestedPayload

class SpeakingEventEnvelope(BaseModel):
    eventId: UUID
    idempotencyKey: UUID
    eventType: str
    schemaVersion: str = "1.0"
    occurredAt: datetime
    producedAt: datetime
    traceId: Optional[str] = None
    correlationId: Optional[str] = None
    source: str
    retryCount: int = 0
    payload: SpeakingEvaluationRequestedPayload
