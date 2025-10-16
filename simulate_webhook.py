#!/usr/bin/env python3
"""
Simula un webhook di ACube per testare il completamento del pagamento
"""

import sys
import os
import json

# Setup path
os.chdir('/Users/lorenzo/aaa_codice/Frappe/frappe-bench')
sys.path.insert(0, 'apps')

import frappe

def main():
    frappe.init(site='mysite.local')
    frappe.connect()
    frappe.set_user('Administrator')

    from solede_openbanking.api.webhooks import handle_payment_webhook

    # Simula payload webhook da ACube per pagamento OBP-0629
    payload = {
        "fiscalId": "12345678901",
        "paymentUuid": "c8e7551e-9761-4767-ad7b-b07121ba9a67",
        "paymentDirection": "outbound",
        "paymentStatus": "completed",
        "amount": "1.00",
        "currencyCode": "EUR",
        "endToEndId": "E2E-OBP-0629",
        "description": "Test payment OBP-0629"
    }

    print(f"\n{'='*80}")
    print(f"SIMULAZIONE WEBHOOK PAGAMENTO COMPLETATO")
    print('='*80)
    print(f"\nPayload:")
    print(json.dumps(payload, indent=2))

    # Chiama handler webhook
    try:
        result = handle_payment_webhook(
            payload=payload,
            company="CB Medical srl",
            log_name="test-webhook-simulation"
        )

        print(f"\n{'='*80}")
        print(f"RISULTATO WEBHOOK")
        print('='*80)
        print(json.dumps(result, indent=2))

        frappe.db.commit()
        print("\n✅ Webhook processato con successo!")

        # Verifica Payment Entry
        pe = frappe.db.get_value("Payment Entry", {"reference_no": "E2E-OBP-0629"}, ["name", "mode_of_payment", "docstatus"], as_dict=1)
        if pe:
            print(f"\n✅ Payment Entry creato: {pe.name}")
            print(f"   Mode of Payment: {pe.mode_of_payment}")
            print(f"   Status: {'Submitted' if pe.docstatus == 1 else 'Draft'}")
        else:
            print("\n⚠️ Payment Entry non trovato")

    except Exception as e:
        print(f"\n❌ ERRORE: {str(e)}")
        import traceback
        traceback.print_exc()
        frappe.db.rollback()

    frappe.destroy()

if __name__ == "__main__":
    main()
