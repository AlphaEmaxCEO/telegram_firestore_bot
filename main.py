sdr_wallet_bot
import# sdr_wallet_bot.py
import os
import logging
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext
import firebase_admin
from firebase_admin import credentials, firestore

# -------------------------------
# CONFIGURATION
# -------------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN")

# Your IDs
OWNER_ID = 8058663737
ASSISTANT_ID = 6677661793

# Listing fee
LISTING_FEE_PERCENT = 20

# Firebase setup
cred = credentials.Certificate("firebase-adminsdk.json")  # your Firebase JSON key file
firebase_admin.initialize_app(cred)
db = firestore.client()

# Logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# -------------------------------
# BOT COMMANDS
# -------------------------------

def start(update: Update, context: CallbackContext):
    update.message.reply_text(
        f"Welcome to SDR Elite Networking Wallet Bot!\n"
        f"Use /balance to check wallet or /submit_product to submit a product."
    )

# Check wallet balance
def balance(update: Update, context: CallbackContext):
    user_id = str(update.effective_user.id)
    wallet_ref = db.collection('wallets').document(user_id)
    wallet = wallet_ref.get()

    balance = wallet.to_dict()['balance'] if wallet.exists else 0
    update.message.reply_text(f"💰 Your wallet balance: {balance} CFA")

# Submit a product for approval
def submit_product(update: Update, context: CallbackContext):
    user_id = str(update.effective_user.id)
    args = context.args

    if not args or len(args) < 2:
        update.message.reply_text("Usage: /submit_product <ProductName> <Price>")
        return

    product_name = args[0]
    try:
        price = float(args[1])
    except ValueError:
        update.message.reply_text("Price must be a number.")
        return

    fee = price * LISTING_FEE_PERCENT / 100

    product_data = {
        "user_id": user_id,
        "product_name": product_name,
        "price": price,
        "listing_fee": fee,
        "status": "pending_payment"
    }

    db.collection('products').add(product_data)

    update.message.reply_text(
        f"🛒 Product '{product_name}' submitted.\n"
        f"Listing fee: {fee} CFA\n"
        f"Pay with /pay_listing {product_name}"
    )

# Pay listing fee
def pay_listing(update: Update, context: CallbackContext):
    user_id = str(update.effective_user.id)
    args = context.args

    if not args:
        update.message.reply_text("Usage: /pay_listing <ProductName>")
        return

    product_name = args[0]
    products_ref = db.collection('products') \
        .where('user_id', '==', user_id) \
        .where('product_name', '==', product_name).get()

    if not products_ref:
        update.message.reply_text("❌ Product not found or already handled.")
        return

    product_doc = products_ref[0]
    product = product_doc.to_dict()

    # Deduct from wallet
    wallet_ref = db.collection('wallets').document(user_id)
    wallet = wallet_ref.get()
    balance = wallet.to_dict()['balance'] if wallet.exists else 0

    if balance < product['listing_fee']:
        update.message.reply_text(
            f"❌ Insufficient funds!\nFee: {product['listing_fee']} CFA\nYour balance: {balance} CFA"
        )
        return

    wallet_ref.set({"balance": balance - product['listing_fee']})

    product_doc.reference.update({"status": "pending_approval"})

    update.message.reply_text("✅ Payment successful! Admin will review your product.")

    # Notify owner & assistant
    context.bot.send_message(
        OWNER_ID,
        f"📩 New product pending approval:\n"
        f"Name: {product_name}\n"
        f"Price: {product['price']} CFA\n"
        f"Seller ID: {user_id}"
    )

    context.bot.send_message(
        ASSISTANT_ID,
        f"📩 New product pending approval:\n"
        f"Name: {product_name}\n"
        f"Price: {product['price']} CFA\n"
        f"Seller ID: {user_id}"
    )

# Approve product (Admin only)
def approve_product(update: Update, context: CallbackContext):
    admin_id = update.effective_user.id

    if admin_id != OWNER_ID and admin_id != ASSISTANT_ID:
        update.message.reply_text("🚫 You are not authorized.")
        return

    args = context.args
    if not args:
        update.message.reply_text("Usage: /approve_product <ProductName>")
        return

    product_name = args[0]

    products_ref = db.collection('products') \
        .where('product_name', '==', product_name) \
        .where('status', '==', 'pending_approval').get()

    if not products_ref:
        update.message.reply_text("❌ No pending product found.")
        return

    product_doc = products_ref[0]
    product_doc.reference.update({"status": "approved"})

    group_id = os.environ.get("GROUP_CHAT_ID")

    context.bot.send_message(
        group_id,
        f"🛍️ New Verified Product!\n"
        f"Product: {product_name}\n"
        f"Price: {product_doc.to_dict()['price']} CFA\n"
        f"Approved by admin."
    )

    update.message.reply_text(f"✅ Product '{product_name}' approved & posted.")

# Deny product
def deny_product(update: Update, context: CallbackContext):
    admin_id = update.effective_user.id

    if admin_id != OWNER_ID and admin_id != ASSISTANT_ID:
        update.message.reply_text("🚫 You are not authorized.")
        return

    args = context.args
    if not args:
        update.message.reply_text("Usage: /deny_product <ProductName>")
        return

    product_name = args[0]

    products_ref = db.collection('products') \
        .where('product_name', '==', product_name) \
        .where('status', '==', 'pending_approval').get()

    if not products_ref:
        update.message.reply_text("❌ No pending product found.")
        return

    product_doc = products_ref[0]
    seller_id = product_doc.to_dict()['user_id']

    product_doc.reference.update({"status": "denied"})

    update.message.reply_text(f"❌ Product '{product_name}' denied.")

    # Notify seller
    context.bot.send_message(
        seller_id,
        f"❌ Your product '{product_name}' has been denied by admin."
    )


# -------------------------------
# MAIN8
# -------------------------------
def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("balance", balance))
    dp.add_handler(CommandHandler("submit_product", submit_product, pass_args=True))
    dp.add_handler(CommandHandler("pay_listing", pay_listing, pass_args=True))
    dp.add_handler(CommandHandler("approve_product", approve_product, pass_args=True))
    dp.add_handler(CommandHandler("deny_product", deny_product, pass_args=True))

    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
