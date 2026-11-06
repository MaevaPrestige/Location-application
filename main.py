import os
import json
import httpx
from fastapi import FastAPI, Form, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
import stripe

app = FastAPI()

# Configuration Brevo & Stripe depuis les variables d'environnement Render
BREVO_API_KEY = os.environ.get("BREVO_API_KEY")
stripe.api_key = os.environ.get("STRIPE_API_KEY", "sk_test_...")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

CONFIG = {
    "taxe_par_nuit_par_personne": 150.0,
    "key_box_code": "1234",
    "cleaning_status": "En attente de validation",
}

RESERVATIONS_FILE = "reservations.json"

def load_reservations():
    if os.path.exists(RESERVATIONS_FILE):
        with open(RESERVATIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "RES-101": {
            "nom_client": "Jean Dupont",
            "email_relais": "jean.dupont.abc@s.airbnb.com",
            "date_arrivee": "2026-11-10",
            "date_depart": "2026-11-13",
            "nuitees": 3,
            "nb_personnes": 2,
            "taxe_sejour_par_nuit": 150.0,
            "statut_paiement": "En attente"
        }
    }

def save_reservations(data):
    with open(RESERVATIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

@app.get("/", response_class=HTMLResponse)
def home():
    reservations = load_reservations()
    
    # Construction des options pour la liste déroulante des réservations
    options_html = ""
    for res_id, info in reservations.items():
        options_html += f'<option value="{res_id}">{info["nom_client"]} ({res_id}) - {info["email_relais"]}</option>'

    html_content = f"""
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
        <script src="https://cdn.tailwindcss.com"></script>
        <link rel="manifest" href="manifest.json">
        <meta name="theme-color" content="#3926f6">
    </head>
    <body class="bg-slate-50 text-slate-800 pb-12">
        <header class="bg-blue-600 text-white p-4 rounded-2xl shadow-md mb-6 text-center">
            <h1 class="text-xl font-bold">Maeva Prestige</h1>
            <p class="text-xs text-blue-100 mt-1">Application de Gestion & Conciergerie</p>
        </header>

        <div class="max-w-md mx-auto p-4 space-y-4">
            <div class="bg-teal-600 text-white p-4 rounded-2xl shadow-md text-center space-y-2">
                <a href="/clients" class="font-bold text-base text-white block">📋 Historique & Taxe de Séjour</a>
                <a href="/monthly-report" class="font-bold text-base text-white block border-t border-teal-500 pt-2">📊 Rapports Mensuels Propriétaires</a>
            </div>

            <!-- Statut du Ménage & Envoi Automatique (Sans Code) -->
            <div class="bg-white p-4 rounded-2xl shadow-sm border border-slate-100">
                <h2 class="font-semibold text-slate-700 mb-2">🧹 Valider le Ménage & Notifier</h2>
                <p class="text-xl font-medium text-blue-600 mb-3">{CONFIG['cleaning_status']}</p>
                <form action="/update-cleaning" method="POST" class="space-y-3">
                    <div>
                        <label class="text-xs text-slate-500 block mb-1">Sélectionner la réservation</label>
                        <select name="res_id" class="w-full p-2 border rounded-xl text-sm bg-white" required>
                            {options_html}
                        </select>
                    </div>
                    <button type="submit" class="w-full bg-emerald-500 text-white p-3 rounded-xl font-bold text-base">Valider Ménage & Envoyer lien de paiement</button>
                </form>
                <p class="text-xs text-slate-400 mt-2">Le client recevra le lien de paiement. Le code d'entrée ne sera envoyé qu'après validation du paiement par Stripe.</p>
            </div>

            <!-- Code Boîte à clés -->
            <div class="bg-white p-4 rounded-2xl shadow-sm border border-slate-100">
                <h2 class="font-semibold text-slate-700 mb-2">🔐 Boîte à clés (Actuel)</h2>
                <p class="text-2xl font-mono font-bold text-slate-800 tracking-widest text-center bg-slate-100 py-3 rounded-xl mb-3">{CONFIG['key_box_code']}</p>
                <form action="/update-key" method="POST" class="space-y-2">
                    <input type="text" name="new_key" placeholder="Nouveau code..." class="w-full p-2 border rounded-xl text-sm" required>
                    <button type="submit" class="w-full bg-slate-800 text-white p-2 rounded-xl text-sm font-medium">Modifier le code</button>
                </form>
            </div>
        </div>
    </body>
    </html>
    """
    return html_content

@app.post("/update-cleaning")
async def update_cleaning(res_id: str = Form(...)):
    reservations = load_reservations()
    if res_id not in reservations:
        return RedirectResponse(url="/", status_code=303)

    res = reservations[res_id]
    CONFIG["cleaning_status"] = f"Validé pour {res['nom_client']}"
    
    nb_pers = res.get("nb_personnes", 2)
    nuitees = res.get("nuitees", 1)
    taxe_nuit = res.get("taxe_sejour_par_nuit", 150.0)
    total_tax = int(taxe_nuit * nuitees * nb_pers)
    email_relais = res.get("email_relais")

    # Création de la session Stripe avec les métadonnées (pour identifier la réservation au paiement)
    checkout_url = "https://location-application.onrender.com/"
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": "xpf",
                        "product_data": {"name": f"Taxe de séjour - {res['nom_client']} ({res_id})"},
                        "unit_amount": total_tax,
                    },
                    "quantity": 1,
                }
            ],
            mode="payment",
            success_url="https://location-application.onrender.com/",
            cancel_url="https://location-application.onrender.com/",
            metadata={
                "res_id": res_id,
                "email_relais": email_relais
            }
        )
        checkout_url = session.url
    except Exception:
        pass

    # Envoi du premier e-mail via Brevo (SANS LE CODE D'ENTRÉE)
    if BREVO_API_KEY and email_relais:
        url = "https://api.brevo.com/v3/smtp/email"
        headers = {
            "api-key": BREVO_API_KEY,
            "content-type": "application/json",
            "accept": "application/json"
        }
        email_payload = {
            "sender": {"name": "Maeva Prestige", "email": "contact@maevaprestige.com"},
            "to": [{"email": email_relais}],
            "subject": "Votre logement est prêt - Taxe de séjour à régler",
            "htmlContent": f"""
                <p>Bonjour {res['nom_client']},</p>
                <p>Votre logement préparé par <b>Maeva Prestige</b> est désormais libre et prêt à vous accueillir !</p>
                <p>Pour finaliser votre arrivée et recevoir immédiatement votre code d'accès à la boîte à clés, merci de bien vouloir régler la taxe de séjour d'un montant de <b>{total_tax} XPF</b> en cliquant sur le lien sécurisé ci-dessous :</p>
                <p><a href="{checkout_url}" style="background:#008489; color:white; padding:10px 20px; text-decoration:none; border-radius:5px; font-weight:bold; display:inline-block;">Régler la taxe de séjour</a></p>
                <p>À très vite !</p>
            """
        }
        async with httpx.AsyncClient() as client:
            try:
                await client.post(url, json=email_payload, headers=headers)
            except Exception:
                pass

    return RedirectResponse(url="/", status_code=303)

@app.post("/stripe-webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("Stripe-Signature")

    try:
        if STRIPE_WEBHOOK_SECRET:
            event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
        else:
            event = json.loads(payload.decode('utf-8'))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Quand le paiement est validé avec succès par Stripe
    if event.get("type") == "checkout.session.completed":
        session = event.get("data", {}).get("object", {})
        metadata = session.get("metadata", {})
        res_id = metadata.get("res_id")
        email_relais = metadata.get("email_relais")

        if res_id:
            reservations = load_reservations()
            if res_id in reservations:
                reservations[res_id]["statut_paiement"] = "Payé"
                save_reservations(reservations)

                # ENVOI AUTOMATIQUE DU CODE DE LA BOÎTE À CLÉS (Puisque c'est payé)
                if BREVO_API_KEY and email_relais:
                    url = "https://api.brevo.com/v3/smtp/email"
                    headers = {
                        "api-key": BREVO_API_KEY,
                        "content-type": "application/json",
                        "accept": "application/json"
                    }
                    email_payload = {
                        "sender": {"name": "Maeva Prestige", "email": "contact@maevaprestige.com"},
                        "to": [{"email": email_relais}],
                        "subject": "Paiement validé - Votre code d'accès Boîte à clés",
                        "htmlContent": f"""
                            <p>Merci ! Votre paiement de la taxe de séjour a bien été validé.</p>
                            <p>Voici votre code d'accès personnel pour la boîte à clés :</p>
                            <h2 style="color: #008489; font-size: 24px; font-family: monospace;">{CONFIG['key_box_code']}</h2>
                            <p>Nous vous souhaitons un excellent séjour à Moorea !</p>
                        """
                    }
                    async with httpx.AsyncClient() as client:
                        try:
                            await client.post(url, json=email_payload, headers=headers)
                        except Exception:
                            pass

    return {"status": "success"}

@app.post("/update-key")
def update_key(new_key: str = Form(...)):
    CONFIG["key_box_code"] = new_key
    return RedirectResponse(url="/", status_code=303)

@app.get("/clients", response_class=HTMLResponse)
def page_clients():
    reservations = load_reservations()
    html_content = """
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Historique & Taxe de Séjour</title>
        <style>
            body { font-family: system-ui, sans-serif; padding: 15px; background: #f4f6f8; }
            .card { background: white; padding: 15px; border-radius: 12px; margin-bottom: 15px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }
            h2 { color: #333; margin-top: 0; }
            label { display: block; margin: 8px 0 3px; font-weight: bold; font-size: 13px; color: #555; }
            input { width: 100%; padding: 8px; font-size: 14px; border: 1px solid #ccc; border-radius: 6px; box-sizing: border-box; }
            .row { display: flex; gap: 10px; margin-bottom: 5px; }
            .row > div { flex: 1; }
            button { background: #008489; color: white; border: none; padding: 10px; width: 100%; border-radius: 6px; font-weight: bold; font-size: 14px; margin-top: 10px; cursor: pointer; }
            .btn-pdf { display: block; text-align: center; background: #2b6cb0; color: white; text-decoration: none; padding: 10px; border-radius: 6px; font-weight: bold; font-size: 14px; margin-top: 8px; }
            .back-link { display: inline-block; margin-bottom: 15px; color: #008489; font-weight: bold; text-decoration: none; }
            .badge { display: inline-block; padding: 3px 8px; border-radius: 12px; font-size: 12px; font-weight: bold; background: #e6fffa; color: #234e52; }
        </style>
    </head>
    <body>
        <a href="/" class="back-link">← Retour à l'accueil</a>
        <h2>Historique des Séjours & Taxes</h2>
    """
    for res_id, info in reservations.items():
        nb_pers = info.get("nb_personnes", 2)
        nuitees = info.get("nuitees", 1)
        taxe_nuit = info.get("taxe_sejour_par_nuit", 150.0)
        total_taxe = taxe_nuit * nuitees * nb_pers
        date_arr = info.get("date_arrivee", "")
        date_dep = info.get("date_depart", "")

        html_content += f"""
        <div class="card">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <h3>{info['nom_client']} ({res_id})</h3>
                <span class="badge">{info.get('statut_paiement', 'En attente')}</span>
            </div>
            <p style="font-size: 13px; color: #666; margin: 2px 0;"><strong>Relais :</strong> {info.get('email_relais', 'N/A')}</p>
            <p style="font-size: 14px; margin: 4px 0;"><strong>Dates :</strong> Du {date_arr} au {date_dep} ({nuitees} nuit(s))</p>
            <p style="font-size: 14px; margin: 4px 0;"><strong>Voyageurs :</strong> {nb_pers} personne(s)</p>
            <p style="font-size: 16px; color: #2b6cb0; margin: 8px 0;"><strong>Total taxe due : {total_taxe:.0f} XPF</strong></p>
            
            <form action="/update-taxe/{res_id}" method="POST">
                <div class="row">
                    <div>
                        <label>Date Arrivée :</label>
                        <input type="date" name="date_arrivee" value="{date_arr}" required>
                    </div>
                    <div>
                        <label>Date Départ :</label>
                        <input type="date" name="date_depart" value="{date_dep}" required>
                    </div>
                </div>
                <div class="row">
                    <div>
                        <label>Voyageurs :</label>
                        <input type="number" name="nb_personnes" value="{nb_pers}" required>
                    </div>
                    <div>
                        <label>Nuits :</label>
                        <input type="number" name="nuitees" value="{nuitees}" required>
                    </div>
                </div>
                <label>Taxe / pers / nuit (XPF) :</label>
                <input type="number" step="1" name="taxe_par_nuit" value="{taxe_nuit}" required>
                <label>E-mail relais (Airbnb/Booking) :</label>
                <input type="text" name="email_relais" value="{info.get('email_relais', '')}" required>
                
                <button type="submit">Mettre à jour les infos</button>
            </form>
            
            <a href="/receipt/{res_id}" target="_blank" class="btn-pdf">📄 Télécharger / Imprimer Reçu PDF</a>
        </div>
        """
    html_content += """
    </body>
    </html>
    """
    return html_content

@app.post("/update-taxe/{res_id}")
def update_taxe_client(
    res_id: str, 
    taxe_par_nuit: float = Form(...),
    date_arrivee: str = Form(...),
    date_depart: str = Form(...),
    nb_personnes: int = Form(...),
    nuitees: int = Form(...),
    email_relais: str = Form(...)
):
    reservations = load_reservations()
    if res_id in reservations:
        reservations[res_id]["taxe_sejour_par_nuit"] = taxe_par_nuit
        reservations[res_id]["date_arrivee"] = date_arrivee
        reservations[res_id]["date_depart"] = date_depart
        reservations[res_id]["nb_personnes"] = nb_personnes
        reservations[res_id]["nuitees"] = nuitees
        reservations[res_id]["email_relais"] = email_relais
        save_reservations(reservations)
    return RedirectResponse(url="/clients", status_code=303)

@app.get("/receipt/{res_id}", response_class=HTMLResponse)
def generate_receipt(res_id: str):
    reservations = load_reservations()
    if res_id not in reservations:
        return RedirectResponse(url="/clients")
    
    info = reservations[res_id]
    nb_pers = info.get("nb_personnes", 2)
    nuitees = info.get("nuitees", 1)
    taxe_nuit = info.get("taxe_sejour_par_nuit", 150.0)
    total_taxe = taxe_nuit * nuitees * nb_pers

    html_content = f"""
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <title>Reçu Taxe de Séjour - {res_id}</title>
        <style>
            body {{ font-family: system-ui, sans-serif; margin: 40px; color: #333; }}
            .header {{ text-align: center; border-bottom: 2px solid #008489; padding-bottom: 20px; }}
            .details {{ margin: 30px 0; font-size: 16px; line-height: 1.6; }}
            .table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
            .table th, .table td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
            .table th {{ background-color: #f4f6f8; }}
            .total {{ font-size: 18px; font-weight: bold; text-align: right; margin-top: 20px; color: #008489; }}
            .print-btn {{ display: block; width: 200px; margin: 30px auto; padding: 12px; text-align: center; background: #008489; color: white; text-decoration: none; border-radius: 6px; font-weight: bold; cursor: pointer; }}
            @media print {{
                .print-btn {{ display: none; }}
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Maeva Prestige - Moorea</h1>
            <p>Justificatif de Paiement - Taxe de Séjour</p>
        </div>
        
        <div class="details">
            <p><strong>Référence Réservation :</strong> {res_id}</p>
            <p><strong>Nom du Voyageur :</strong> {info['nom_client']}</p>
            <p><strong>Dates du séjour :</strong> Du {info.get('date_arrivee', 'N/A')} au {info.get('date_depart', 'N/A')}</p>
        </div>

        <table class="table">
            <thead>
                <tr>
                    <th>Désignation</th>
                    <th>Nombre de voyageurs</th>
                    <th>Nombre de nuits</th>
                    <th>Tarif / pers / nuit</th>
                    <th>Total</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>Taxe de séjour forfaitaire</td>
                    <td>{nb_pers}</td>
                    <td>{nuitees}</td>
                    <td>{taxe_nuit:.0f} XPF</td>
                    <td><strong>{total_taxe:.0f} XPF</strong></td>
                </tr>
            </tbody>
        </table>

        <div class="total">
            Montant total réglé : {total_taxe:.0f} XPF
        </div>

        <button onclick="window.print()" class="print-btn">🖨️ Imprimer / Sauvegarder PDF</button>
    </body>
    </html>
    """
    return html_content

@app.get("/monthly-report", response_class=HTMLResponse)
def monthly_report_selector():
    reservations = load_reservations()
    months = set()
    for info in reservations.values():
        arr = info.get("date_arrivee", "")
        if len(arr) >= 7:
            months.add(arr[:7])
    
    sorted_months = sorted(list(months), reverse=True)
    if not sorted_months:
        sorted_months = ["2026-11"]

    html_content = """
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Rapports Mensuels Propriétaires</title>
        <style>
            body { font-family: system-ui, sans-serif; padding: 15px; background: #f4f6f8; }
            .card { background: white; padding: 20px; border-radius: 12px; margin-bottom: 15px; box-shadow: 0 2px 5px rgba(0,0,0,0.05); text-align: center; }
            h2 { color: #333; margin-top: 0; }
            a.btn { display: block; background: #008489; color: white; text-decoration: none; padding: 12px; border-radius: 8px; font-weight: bold; margin-top: 10px; }
            .back-link { display: inline-block; margin-bottom: 15px; color: #008489; font-weight: bold; text-decoration: none; }
        </style>
    </head>
    <body>
        <a href="/" class="back-link">← Retour à l'accueil</a>
        <h2>Rapports Mensuels - Taxe de Séjour</h2>
        <p style="color: #666; font-size: 14px; margin-bottom: 20px;">Sélectionnez un mois pour générer l'état récapitulatif destiné aux propriétaires :</p>
    """
    for m in sorted_months:
        html_content += f"""
        <div class="card">
            <h3>Mois : {m}</h3>
            <a href="/monthly-report/{m}" class="btn">📄 Générer le Rapport PDF ({m})</a>
        </div>
        """
    html_content += """
    </body>
    </html>
    """
    return html_content

@app.get("/monthly-report/{year_month}", response_class=HTMLResponse)
def generate_monthly_pdf(year_month: str):
    reservations = load_reservations()
    filtered_res = {}
    total_month = 0

    for res_id, info in reservations.items():
        arr = info.get("date_arrivee", "")
        if arr.startswith(year_month):
            nb_pers = info.get("nb_personnes", 2)
            nuitees = info.get("nuitees", 1)
            taxe_nuit = info.get("taxe_sejour_par_nuit", 150.0)
            t_tot = taxe_nuit * nuitees * nb_pers
            filtered_res[res_id] = {**info, "total_taxe": t_tot}
            total_month += t_tot

    rows_html = ""
    for res_id, info in filtered_res.items():
        rows_html += f"""
        <tr>
            <td>{res_id}</td>
            <td>{info['nom_client']}</td>
            <td>{info.get('date_arrivee')} au {info.get('date_depart')}</td>
            <td>{info.get('nb_personnes')}</td>
            <td>{info.get('nuitees')}</td>
            <td><strong>{info['total_taxe']:.0f} XPF</strong></td>
        </tr>
        """

    html_content = f"""
    <!DOCTYPE html>
    <html lang="fr">
    <head>
        <meta charset="UTF-8">
        <title>Rapport Mensuel - {year_month}</title>
        <style>
            body {{ font-family: system-ui, sans-serif; margin: 40px; color: #333; }}
            .header {{ text-align: center; border-bottom: 2px solid #008489; padding-bottom: 20px; }}
            .details {{ margin: 25px 0; font-size: 16px; }}
            .table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
            .table th, .table td {{ border: 1px solid #ddd; padding: 10px; text-align: left; font-size: 14px; }}
            .table th {{ background-color: #f4f6f8; }}
            .total {{ font-size: 18px; font-weight: bold; text-align: right; margin-top: 25px; color: #008489; }}
            .print-btn {{ display: block; width: 220px; margin: 30px auto; padding: 12px; text-align: center; background: #008489; color: white; text-decoration: none; border-radius: 6px; font-weight: bold; cursor: pointer; }}
            @media print {{
                .print-btn {{ display: none; }}
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Maeva Prestige - Moorea</h1>
            <p>Rapport Récapitulatif Mensuel de la Taxe de Séjour</p>
        </div>
        
        <div class="details">
            <p><strong>Mois concerné :</strong> {year_month}</p>
            <p><strong>Établissement :</strong> Location Moorea</p>
        </div>

        <table class="table">
            <thead>
                <tr>
                    <th>Réf</th>
                    <th>Voyageur</th>
                    <th>Dates du séjour</th>
                    <th>Voyageurs</th>
                    <th>Nuits</th>
                    <th>Taxe perçue</th>
                </tr>
            </thead>
            <tbody>
                {rows_html if rows_html else '<tr><td colspan="6" style="text-align:center;">Aucune réservation enregistrée pour ce mois.</td></tr>'}
            </tbody>
        </table>

        <div class="total">
            Total des taxes collectées pour {year_month} : {total_month:.0f} XPF
        </div>

        <button onclick="window.print()" class="print-btn">🖨️ Imprimer / Sauvegarder PDF</button>
    </body>
    </html>
    """
    return html_content
