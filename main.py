import os
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import stripe
from twilio.rest import Client

app = FastAPI()

# Configuration des clés secrètes récupérées via les variables d'environnement Render
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "sk_test_...")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "")

# Initialisation Twilio si les clés sont présentes
twilio_client = None
if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
    try:
        twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    except Exception:
        pass

# Paramètres configurables de l'hébergement (Taxe de séjour / Boîte à clés)
CONFIG = {
    "tax_per_night_per_person": 150.0,
    "key_box_code": "1234",
    "cleaning_status": "En attente de validation",
}


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    html_content = f"""
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
        <title>Gestion Conciergerie</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <link rel="manifest" href="/manifest.json">
        <meta name="theme-color" content="#3b82f6">
    </head>
    <body class="bg-slate-50 text-slate-800 pb-12">
        <div class="max-w-md mx-auto p-4">
            <header class="bg-blue-600 text-white p-4 rounded-2xl shadow-md mb-6 text-center">
                <h1 class="text-xl font-bold">🏖️ Maeva Prestige</h1>
                <p class="text-xs text-blue-100 mt-1">Application de Gestion & Conciergerie</p>
            </header>
<div class="bg-teal-600 text-white p-4 rounded-2xl shadow-md mb-6 text-center">
    <a href="/clients" class="font-bold text-lg text-white block">📋 Gérer la taxe de séjour par client</a>
</div>


            <!-- Statut du Ménage -->
            <div class="bg-white p-4 rounded-2xl shadow-sm mb-4 border border-slate-100">
                <h2 class="font-semibold text-slate-700 mb-2">🧹 Statut du Ménage</h2>
                <p class="text-sm text-slate-500 mb-3">Actuel : <span class="font-medium text-blue-600">{CONFIG["cleaning_status"]}</span></p>
                <form action="/update-cleaning" method="POST" class="flex gap-2">
                    <button type="submit" name="status" value="Validé" class="flex-1 bg-emerald-500 text-white py-2 rounded-xl text-sm font-medium">Valider</button>
                    <button type="submit" name="status" value="À refaire" class="flex-1 bg-amber-500 text-white py-2 rounded-xl text-sm font-medium">À refaire</button>
                </form>
            </div>

            <!-- Code Boîte à clés -->
            <div class="bg-white p-4 rounded-2xl shadow-sm mb-4 border border-slate-100">
                <h2 class="font-semibold text-slate-700 mb-2">🔑 Boîte à clés</h2>
                <p class="text-2xl font-mono font-bold text-slate-800 tracking-widest text-center bg-slate-100 py-3 rounded-xl">{CONFIG["key_box_code"]}</p>
            </div>

            <!-- Paiement Taxe de séjour & Caution -->
            <div class="bg-white p-4 rounded-2xl shadow-sm mb-4 border border-slate-100">
                <h2 class="font-semibold text-slate-700 mb-2">💳 Espace Voyageur (Stripe)</h2>
                <form action="/create-payment" method="POST" class="space-y-3">
                    <div>
                        <label class="text-xs text-slate-500 block mb-1">Nombre de nuits</label>
                        <input type="number" name="nights" value="3" class="w-full p-2 border rounded-xl text-sm" required>
                    </div>
                    <div>
                        <label class="text-xs text-slate-500 block mb-1">Nombre de voyageurs</label>
                        <input type="number" name="guests" value="2" class="w-full p-2 border rounded-xl text-sm" required>
                    </div>
                    <button type="submit" class="w-full bg-blue-600 text-white py-3 rounded-xl font-medium text-sm shadow-sm">Payer Taxe & Caution</button>
                </form>
            </div>

            <!-- Alerte SMS Twilio -->
            <div class="bg-white p-4 rounded-2xl shadow-sm border border-slate-100">
                <h2 class="font-semibold text-slate-700 mb-2">📱 Alerte SMS Rapide</h2>
                <form action="/send-sms" method="POST" class="space-y-3">
                    <input type="text" name="phone" placeholder="Numéro (ex: +336...)" class="w-full p-2 border rounded-xl text-sm" required>
                    <textarea name="message" placeholder="Message..." class="w-full p-2 border rounded-xl text-sm" rows="2" required></textarea>
                    <button type="submit" class="w-full bg-slate-800 text-white py-2 rounded-xl text-sm font-medium">Envoyer SMS</button>
                </form>
            </div>
        </div>
    </body>
    </html>
    """
    return html_content


@app.post("/update-cleaning")
def update_cleaning(status: str = Form(...)):
    CONFIG["cleaning_status"] = status
    return RedirectResponse(url="/", status_code=303)


@app.post("/send-sms")
def send_sms(phone: str = Form(...), message: str = Form(...)):
    if twilio_client and TWILIO_PHONE_NUMBER:
        try:
            twilio_client.messages.create(
                body=message, from_=TWILIO_PHONE_NUMBER, to=phone
            )
        except Exception:
            pass
    return RedirectResponse(url="/", status_code=303)


@app.post("/create-payment")
def create_payment(nights: int = Form(...), guests: int = Form(...)):
    total_tax = nights * guests * CONFIG["tax_per_night_per_person"]
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": "eur",
                        "product_data": {"name": "Taxe de séjour & Caution"},
                        "unit_amount": int(total_tax * 100),
                    },
                    "quantity": 1,
                }
            ],
            mode="payment",
            success_url="https://google.com",
            cancel_url="https://google.com",
        )
        return RedirectResponse(url=session.url, status_code=303)
    except Exception:
        return RedirectResponse(url="/", status_code=303)
import json
import os
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

RESERVATIONS_FILE = "reservations.json"

def load_reservations():
    if os.path.exists(RESERVATIONS_FILE):
        with open(RESERVATIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    # Données d'exemple pour tester
    return {
        "RES-101": {
            "nom_client": "Jean Dupont",
            "nuitees": 3,
            "taxe_sejour_par_nuit": 2.50,
            "statut": "Confirmé"
        },
        "RES-102": {
            "nom_client": "Marie Martin",
            "nuitees": 5,
            "taxe_sejour_par_nuit": 2.50,
            "statut": "Confirmé"
        }
    }

def save_reservations(data):
    with open(RESERVATIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
@app.get("/clients", response_class=HTMLResponse)
def page_clients():
    reservations = load_reservations()
    
    html_content = """
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Gestion de la Taxe de Séjour</title>
        <style>
            body { font-family: system-ui, sans-serif; padding: 15px; background: #f4f6f8; }
            .card { background: white; padding: 15px; border-radius: 10px; margin-bottom: 15px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
            h2 { color: #333; margin-top: 0; }
            label { display: block; margin: 10px 0 5px; font-weight: bold; }
            input[type="number"] { width: 100%; padding: 10px; font-size: 16px; border: 1px solid #ccc; border-radius: 5px; box-sizing: border-box; }
            button { background: #008489; color: white; border: none; padding: 12px; width: 100%; border-radius: 5px; font-size: 16px; margin-top: 10px; font-weight: bold; }
        </style>
    </head>
    <body>
        <h2>Taxe de séjour par client</h2>
    """
    
    for res_id, info in reservations.items():
        total_taxe = info['taxe_sejour_par_nuit'] * info['nuitees']
        html_content += f"""
        <div class="card">
            <h3>{info['nom_client']} (Réservation {res_id})</h3>
            <p>Durée du séjour : {info['nuitees']} nuit(s)</p>
            <p><strong>Total taxe due : {total_taxe:.2f} €</strong></p>
            <form action="/update-taxe/{res_id}" method="post">
                <label for="taxe">Taxe par nuit (€) :</label>
                <input type="number" step="0.01" name="taxe_par_nuit" value="{info['taxe_sejour_par_nuit']}">
                <button type="submit">Mettre à jour pour ce client</button>
            </form>
        </div>
        """
        
    html_content += "</body></html>"
    return html_content

@app.post("/update-taxe/{res_id}")
def update_taxe_client(res_id: str, taxe_par_nuit: float = Form(...)):
    reservations = load_reservations()
    if res_id in reservations:
        reservations[res_id]["taxe_sejour_par_nuit"] = taxe_par_nuit
        save_reservations(reservations)
    return RedirectResponse(url="/clients", status_code=303)
RESERVATIONS_FILE = "reservations.json"

def load_reservations():
    if os.path.exists(RESERVATIONS_FILE):
        with open(RESERVATIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "RES-101": {
            "nom_client": "Jean Dupont",
            "nuitees": 3,
            "taxe_sejour_par_nuit": 2.50,
            "statut": "Confirmé"
        }
    }

def save_reservations(data):
    with open(RESERVATIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

@app.get("/clients", response_class=HTMLResponse)
def page_clients():
    reservations = load_reservations()
    html_content = """
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Gestion de la Taxe de Séjour</title>
        <style>
            body { font-family: system-ui, sans-serif; padding: 15px; background: #f4f6f8; }
            .card { background: white; padding: 15px; border-radius: 10px; margin-bottom: 15px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
            h2 { color: #333; margin-top: 10px; }
            label { display: block; margin: 10px 0 5px; font-weight: bold; }
            input[type="number"] { width: 100%; padding: 10px; font-size: 16px; border: 1px solid #ccc; border-radius: 5px; box-sizing: border-box; }
            button { background: #008489; color: white; border: none; padding: 12px; width: 100%; border-radius: 5px; font-size: 16px; margin-top: 10px; font-weight: bold; }
            .back-link { display: inline-block; margin-bottom: 15px; color: #008489; font-weight: bold; text-decoration: none; }
        </style>
    </head>
    <body>
        <a href="/" class="back-link">← Retour à l'accueil</a>
        <h2>Taxe de séjour par client</h2>
    """
    for res_id, info in reservations.items():
        total_taxe = info['taxe_sejour_par_nuit'] * info['nuitees']
        html_content += f"""
        <div class="card">
            <h3>{info['nom_client']} (Réservation {res_id})</h3>
            <p>Durée du séjour : {info['nuitees']} nuit(s)</p>
            <p><strong>Total taxe due : {total_taxe:.2f} €</strong></p>
            <form action="/update-taxe/{res_id}" method="post">
                <label for="taxe">Taxe par nuit (€) :</label>
                <input type="number" step="0.01" name="taxe_par_nuit" value="{info['taxe_sejour_par_nuit']}">
                <button type="submit">Mettre à jour pour ce client</button>
            </form>
        </div>
        """
    html_content += "</body></html>"
    return html_content

@app.post("/update-taxe/{res_id}")
def update_taxe_client(res_id: str, taxe_par_nuit: float = Form(...)):
    reservations = load_reservations()
    if res_id in reservations:
        reservations[res_id]["taxe_sejour_par_nuit"] = taxe_par_nuit
        save_reservations(reservations)
    return RedirectResponse(url="/clients", status_code=303)
