from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("transactions", "0006_transaction_balance_after_transaction_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="transaction",
            name="channel",
            field=models.CharField(
                blank=True,
                choices=[
                    ("", "sin dato"),
                    ("manual", "manual"),
                    ("card_present", "tarjeta presente"),
                    ("ecommerce", "ecommerce"),
                    ("bank_transfer", "transferencia bancaria"),
                    ("wallet", "wallet"),
                    ("sms", "sms"),
                    ("email", "email"),
                    ("voice", "voz"),
                    ("message_inferred", "mensaje inferido"),
                    ("api", "api"),
                    ("import", "importacion"),
                    ("other", "otro"),
                ],
                default="",
                help_text="Canal canonico del movimiento: ecommerce, sms, email, api, etc.",
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name="transactionexternaldetails",
            name="channel",
            field=models.CharField(
                blank=True,
                choices=[
                    ("", "sin dato"),
                    ("manual", "manual"),
                    ("card_present", "tarjeta presente"),
                    ("ecommerce", "ecommerce"),
                    ("bank_transfer", "transferencia bancaria"),
                    ("wallet", "wallet"),
                    ("sms", "sms"),
                    ("email", "email"),
                    ("voice", "voz"),
                    ("message_inferred", "mensaje inferido"),
                    ("api", "api"),
                    ("import", "importacion"),
                    ("other", "otro"),
                ],
                default="",
                max_length=32,
            ),
        ),
    ]
