import json
import subprocess

import click
from opshin.prelude import TxOutRef, TxId
from pycardano import (
    OgmiosChainContext,
    TransactionBuilder,
    TransactionOutput,
    PlutusV2Script,
    MultiAsset,
    RedeemerTag,
    Redeemer,
    plutus_script_hash,
    Value,
)

from src.utils import get_address, get_signing_info, network, ogmios_url
from src.week05 import assets_dir, lecture_dir


@click.command()
@click.argument("wallet_name")
@click.argument("token_name")
@click.option(
    "--amount",
    type=int,
    default=1,
)
@click.option(
    "--script",
    type=click.Choice(["free", "nft", "signed"]),
    default="nft",
)
def main(
    wallet_name: str,
    token_name: str,
    amount: int,
    script: str,
):
    # Load chain context
    context = OgmiosChainContext(ogmios_url, network=network)

    # Get payment address
    payment_address = get_address(wallet_name)

    # Get input utxo
    utxo_to_spend = None
    for utxo in context.utxos(str(payment_address)):
        if utxo.output.amount.coin > 3000000:
            utxo_to_spend = utxo
            break
    assert utxo_to_spend is not None, "UTxO not found to spend!"

    tn_bytes = bytes(token_name, encoding="utf-8")
    signatures = []
    if script == "nft":
        # Build script
        save_path = assets_dir.joinpath(f"nft_{token_name}")
        script_path = lecture_dir.joinpath("nft.py")
        oref = TxOutRef(
            id=TxId(bytes(utxo_to_spend.input.transaction_id)),
            idx=utxo_to_spend.input.index,
        )
        tn_bytes = bytes(token_name, encoding="utf-8")
        tn_json = json.dumps({"bytes": tn_bytes.hex()})
        subprocess.run(
            [
                "opshin",
                "-o",
                str(save_path),
                "build",
                str(script_path),
                oref.to_json(),
                tn_json,
            ],
            check=True,
        )
        cbor_path = save_path.joinpath("script.cbor")
    elif script == "signed":
        # Build script
        save_path = assets_dir.joinpath(f"signed_{wallet_name}")
        script_path = lecture_dir.joinpath("signed.py")
        pkh = bytes(get_address(wallet_name).payment_part)
        signatures.append(pkh)
        pkh_json = json.dumps({"bytes": pkh.hex()})
        subprocess.run(
            [
                "opshin",
                "-o",
                str(save_path),
                "build",
                str(script_path),
                pkh_json,
            ],
            check=True,
        )
        cbor_path = save_path.joinpath("script.cbor")
    else:
        cbor_path = assets_dir.joinpath(script, "script.cbor")

    # Load script info
    with open(cbor_path, "r") as f:
        cbor_hex = f.read()
    cbor = bytes.fromhex(cbor_hex)
    plutus_script = PlutusV2Script(cbor)
    script_hash = plutus_script_hash(plutus_script)

    # Build the transaction
    builder = TransactionBuilder(context)
    builder.add_minting_script(
        script=plutus_script, redeemer=Redeemer(RedeemerTag.MINT, 0)
    )
    builder.mint = MultiAsset.from_primitive({bytes(script_hash): {tn_bytes: amount}})
    builder.add_input(utxo_to_spend)
    builder.add_output(
        TransactionOutput(
            payment_address, amount=Value(coin=2000000, multi_asset=builder.mint)
        )
    )
    builder.required_signers = signatures

    # Sign the transaction
    payment_vkey, payment_skey, payment_address = get_signing_info(wallet_name)
    signed_tx = builder.build_and_sign(
        signing_keys=[payment_skey],
        change_address=payment_address,
    )

    # Submit the transaction
    context.submit_tx(signed_tx.to_cbor())

    print(f"transaction id: {signed_tx.id}")
    print(f"Cardanoscan: https://preview.cardanoscan.io/transaction/{signed_tx.id}")


if __name__ == "__main__":
    main()