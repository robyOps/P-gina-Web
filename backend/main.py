import os
from datetime import datetime, date
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(title="Notaría Pública API", version="1.0.0")

# Enable CORS for all origins by default to simplify deployment with separate frontends
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class InfoResponse(BaseModel):
    nombreNotaria: str
    direccion: str
    horario: List[str]
    telefonos: List[str]
    correo: str
    mapa: Optional[str] = None


class Tramite(BaseModel):
    id: int
    nombre: str
    descripcion: str
    requisitos: List[str]


class Arancel(BaseModel):
    codigo: str
    nombre: str
    monto: float
    moneda: str
    vigenteDesde: date


class Personal(BaseModel):
    nombre: str
    cargo: str
    remuneracion: float


class Informe(BaseModel):
    titulo: str
    fecha: date
    url: str


class Compareciente(BaseModel):
    nombre: str


class Indice(BaseModel):
    numero: str
    fecha: date
    tipo: str
    comparecientes: List[Compareciente]


class ReclamoRequest(BaseModel):
    nombre: str
    correo: str
    mensaje: str


class AdminToken(BaseModel):
    token: str = Field(..., description="Token de autenticación para administradores")


class AdminInformeRequest(AdminToken):
    titulo: str
    fecha: date
    url: str


class AdminArancelRequest(AdminToken):
    codigo: str
    nombre: str
    monto: float
    moneda: str
    vigenteDesde: date


class AdminIndiceEntry(BaseModel):
    numero: str
    fecha: date
    tipo: str
    comparecientes: List[Compareciente]


class AdminIndiceRequest(AdminToken):
    registros: List[AdminIndiceEntry]


ADMIN_TOKEN_ENV = "ADMIN_TOKEN"
RECLAMO_LOG_PATH = os.environ.get("RECLAMO_LOG_PATH", "reclamos.log")


# Simple in-memory data store
info_data = InfoResponse(
    nombreNotaria="Notaría Ejemplo Santiago",
    direccion="Av. Libertador Bernardo O'Higgins 1234, Santiago, Chile",
    horario=[
        "Lunes a Viernes: 09:00 - 18:00",
        "Sábado: 09:00 - 13:00",
    ],
    telefonos=["+56 2 2345 6789", "+56 9 8765 4321"],
    correo="contacto@notariaejemplo.cl",
    mapa="https://maps.google.com/?q=-33.4489,-70.6693",
)

tramites_data: List[Tramite] = [
    Tramite(
        id=1,
        nombre="Autorización de firma",
        descripcion="Validación de firmas para documentos oficiales.",
        requisitos=["Cédula de identidad vigente", "Documento a firmar"],
    ),
    Tramite(
        id=2,
        nombre="Poder simple",
        descripcion="Emisión de poder simple para trámites administrativos.",
        requisitos=[
            "Cédula de identidad del mandante",
            "Datos del mandatario",
            "Detalle de facultades",
        ],
    ),
]

aranceles_data: List[Arancel] = [
    Arancel(
        codigo="A-001",
        nombre="Autorización de firma",
        monto=5000.0,
        moneda="CLP",
        vigenteDesde=date(2024, 1, 1),
    ),
    Arancel(
        codigo="A-002",
        nombre="Poder simple",
        monto=8500.0,
        moneda="CLP",
        vigenteDesde=date(2023, 9, 1),
    ),
]

personal_data: List[Personal] = [
    Personal(nombre="María González", cargo="Notaria Titular", remuneracion=2500000.0),
    Personal(nombre="Juan Pérez", cargo="Oficial Primero", remuneracion=1500000.0),
    Personal(nombre="Carolina Soto", cargo="Secretaria", remuneracion=950000.0),
]

informes_data: List[Informe] = [
    Informe(
        titulo="Informe de Fiscalización 2024-03",
        fecha=date(2024, 3, 15),
        url="https://notariaejemplo.cl/informes/2024-03.pdf",
    ),
    Informe(
        titulo="Informe de Fiscalización 2023-12",
        fecha=date(2023, 12, 10),
        url="https://notariaejemplo.cl/informes/2023-12.pdf",
    ),
    Informe(
        titulo="Informe de Fiscalización 2023-08",
        fecha=date(2023, 8, 21),
        url="https://notariaejemplo.cl/informes/2023-08.pdf",
    ),
]

indices_data: List[Indice] = [
    Indice(
        numero="2024-001",
        fecha=date(2024, 4, 2),
        tipo="Escritura Pública",
        comparecientes=[
            Compareciente(nombre="María López"),
            Compareciente(nombre="Carlos Díaz"),
        ],
    ),
    Indice(
        numero="2024-002",
        fecha=date(2024, 4, 5),
        tipo="Poder",
        comparecientes=[
            Compareciente(nombre="Juan Torres"),
            Compareciente(nombre="Ana Silva"),
        ],
    ),
]


def verify_admin_token(token: str) -> None:
    expected_token = os.environ.get(ADMIN_TOKEN_ENV)
    if not expected_token or token != expected_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de administrador inválido",
        )


@app.get("/public/info", response_model=InfoResponse)
def get_info() -> InfoResponse:
    return info_data


@app.get("/public/tramites", response_model=List[Tramite])
def get_tramites() -> List[Tramite]:
    return tramites_data


@app.get("/public/aranceles", response_model=List[Arancel])
def get_aranceles() -> List[Arancel]:
    return sorted(aranceles_data, key=lambda a: a.vigenteDesde, reverse=True)


@app.get("/public/personal", response_model=List[Personal])
def get_personal() -> List[Personal]:
    return personal_data


@app.get("/public/informes", response_model=List[Informe])
def get_informes() -> List[Informe]:
    sorted_informes = sorted(informes_data, key=lambda i: i.fecha, reverse=True)
    return sorted_informes[:3]


@app.get("/public/indices", response_model=List[Indice])
def get_indices(q: Optional[str] = None, fecha: Optional[str] = None) -> List[Indice]:
    results = indices_data
    if q:
        query_lower = q.lower()
        results = [
            indice
            for indice in results
            if any(query_lower in compareciente.nombre.lower() for compareciente in indice.comparecientes)
        ]
    if fecha:
        try:
            year, month = fecha.split("-")
            year_i = int(year)
            month_i = int(month)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Formato de fecha inválido, use YYYY-MM") from exc
        results = [indice for indice in results if indice.fecha.year == year_i and indice.fecha.month == month_i]
    results_sorted = sorted(results, key=lambda idx: idx.fecha, reverse=True)
    return results_sorted


@app.post("/public/reclamo", status_code=status.HTTP_201_CREATED)
def create_reclamo(reclamo: ReclamoRequest) -> dict:
    timestamp = datetime.utcnow().isoformat()
    log_entry = f"{timestamp}\t{reclamo.nombre}\t{reclamo.correo}\t{reclamo.mensaje.replace(os.linesep, ' ')}\n"
    with open(RECLAMO_LOG_PATH, "a", encoding="utf-8") as log_file:
        log_file.write(log_entry)
    return {"message": "Reclamo recibido"}


@app.post("/admin/informe", status_code=status.HTTP_201_CREATED)
def add_informe(request: AdminInformeRequest) -> dict:
    verify_admin_token(request.token)
    informe = Informe(titulo=request.titulo, fecha=request.fecha, url=request.url)
    informes_data.append(informe)
    return {"message": "Informe agregado", "informe": informe}


@app.post("/admin/arancel", status_code=status.HTTP_201_CREATED)
def add_or_update_arancel(request: AdminArancelRequest) -> dict:
    verify_admin_token(request.token)
    existing = next((a for a in aranceles_data if a.codigo == request.codigo), None)
    arancel = Arancel(
        codigo=request.codigo,
        nombre=request.nombre,
        monto=request.monto,
        moneda=request.moneda,
        vigenteDesde=request.vigenteDesde,
    )
    if existing:
        aranceles_data.remove(existing)
    aranceles_data.append(arancel)
    return {"message": "Arancel registrado", "arancel": arancel}


@app.post("/admin/indice", status_code=status.HTTP_201_CREATED)
def add_indices(request: AdminIndiceRequest) -> dict:
    verify_admin_token(request.token)
    nuevos_indices = [
        Indice(
            numero=registro.numero,
            fecha=registro.fecha,
            tipo=registro.tipo,
            comparecientes=registro.comparecientes,
        )
        for registro in request.registros
    ]
    indices_data.extend(nuevos_indices)
    return {"message": "Índices agregados", "agregados": len(nuevos_indices)}


@app.get("/health")
def healthcheck() -> dict:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
