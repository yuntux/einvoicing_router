"""Schémas Pydantic de la ressource `Flow` de l'API AFNOR "Flow Service" (norme
XP Z12-013, v1.3.0 — cf. `backend/docs/afnor-contracts/afnor-flow-openapi-v1.3.0.json`).

Le routeur **émule un PDP** vis-à-vis d'Odoo (spec.md § 4.4) : ces schémas
reproduisent fidèlement les composants du contrat officiel (`CoreFlowInfo`,
`FlowInfo`, `FullFlowInfo`, `Flow`, `Acknowledgement`, `SearchFlowParams`,
`SearchFlowContent`...) pour que le connecteur Odoo puisse dialoguer avec le
routeur exactement comme avec un vrai PDP — pas une API maison qui s'en inspire."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

FlowSyntax = Literal["CII", "UBL", "Factur-X", "CDAR", "FRR"]
FlowProfile = Literal["Basic", "CIUS", "Extended-CTC-FR", "Undefined"]
ProcessingRule = Literal[
    "B2B",
    "B2BInt",
    "B2C",
    "B2G",
    "B2GInt",
    "OutOfScope",
    "B2GOutOfScope",
    "ArchiveOnly",
    "NotApplicable",
    "Undefined",
]
ProcessingRuleSource = Literal["Input", "Computed"]
FlowDirection = Literal["In", "Out"]
FlowAckStatus = Literal["Pending", "Ok", "Error"]

# Seuls les flowType effectivement produits par le routeur aujourd'hui (factures
# reçues) — les autres valeurs du contrat (e-reporting, CDAR sortant...) ne sont pas
# encore émulées, cf. limitations documentées sur les endpoints qui les utiliseraient.
FlowType = Literal[
    "CustomerInvoice",
    "SupplierInvoice",
    "CustomerInvoiceLC",
    "SupplierInvoiceLC",
    "StateCustomerInvoiceLC",
    "StateSupplierInvoiceLC",
    "AggregatedCustomerTransactionReport",
    "UnitaryCustomerTransactionReport",
    "AggregatedCustomerPaymentReport",
    "UnitaryCustomerPaymentReport",
    "UnitarySupplierTransactionReport",
    "MultiFlowReport",
    "StateCustomerInvoice",
    "StateSupplierInvoice",
    "StateTransactionReport",
    "StateTransactionReportLC",
    "StatePaymentReport",
    "StatePaymentReportLC",
    "Undefined",
]


class AcknowledgementDetail(BaseModel):
    item: str
    level: Literal["Error", "Warning"]
    reasonCode: str
    reasonMessage: str


class Acknowledgement(BaseModel):
    status: FlowAckStatus
    details: list[AcknowledgementDetail] | None = None


class FlowInfoIn(BaseModel):
    """Corps du champ `flowInfo` (JSON) de `POST /flows` (multipart)."""

    flowSyntax: FlowSyntax
    name: str = Field(max_length=255)
    flowProfile: FlowProfile | None = None
    processingRule: ProcessingRule | None = None
    trackingId: str | None = Field(default=None, max_length=64)


class FullFlowInfo(FlowInfoIn):
    """Réponse de `POST /flows` (202)."""

    flowId: str
    submittedAt: datetime


class Flow(FullFlowInfo):
    """Réponse d'un élément de `POST /flows/search` ou de `GET /flows/{flowId}`."""

    flowProfile: FlowProfile
    processingRule: ProcessingRule
    processingRuleSource: ProcessingRuleSource
    flowDirection: FlowDirection
    flowType: FlowType
    acknowledgement: Acknowledgement
    updatedAt: datetime


class SearchFlowFiltersIn(BaseModel):
    ackStatus: FlowAckStatus | None = None
    flowDirection: list[FlowDirection] | None = None
    flowType: list[FlowType] | None = None
    processingRule: list[ProcessingRule] | None = None
    trackingId: str | None = None
    updatedAfter: datetime | None = None
    updatedBefore: datetime | None = None


class SearchFlowParamsIn(BaseModel):
    where: SearchFlowFiltersIn
    limit: int = Field(default=25, le=100)
    cursor: str | None = None


class SearchFlowContentOut(BaseModel):
    results: list[Flow]
    filters: SearchFlowFiltersIn
    limit: int
    nextCursor: str | None = None
