from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy import Enum
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Enum as PgEnum
from datetime import date, datetime

from flask_login import UserMixin
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.dialects.postgresql import ARRAY
import sqlalchemy.dialects.postgresql as pg
from sqlalchemy.orm import relationship
from app.extensions import db
import enum
from enum import Enum as PyEnum
from sqlalchemy import Enum as SQLEnum
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import ARRAY
# Enums
availability_enum = Enum('Available', 'Busy', 'Away', name='availability_enum')
negotiation_enum = Enum('yes', 'no', 'not sure', name='negotiation_enum')

# ---------------------- USER ----------------------

# ---------------------- USER ----------------------
from datetime import datetime, timedelta
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
 # Adjust if you're importing from another module


from datetime import datetime
from enum import Enum


# Enums
# models/enums.py or models/order_enums.py (or similar)

import enum
# Enums must match DB enum values (usually lowercase)
class PaymentStatus(enum.Enum):
    pending = "pending"
    completed = "completed"


class OrderStatus(enum.Enum):
    INITIATED = "initiated"
    PROCESSING = "processing"
    DELIVERED = "delivered"



from enum import Enum


class StatusEnum(Enum):
    pending = "pending"
    accepted = "accepted"
    shipped = "shipped"
    completed = "completed"
    canceled = "canceled"
    success = "success"
    failed = "failed"

    def __str__(self):
        return self.value




# ------------------ ORDER MODEL ------------------
class Order(db.Model):
    __tablename__ = 'orders'

    id = db.Column(db.Integer, primary_key=True)
    buyer_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    seller_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    agent_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    agreed_price = db.Column(db.Float, nullable=False)
    total_amount = db.Column(db.Float, nullable=False)  # agreed_price × quantity
    escrow_id = db.Column(db.Integer, db.ForeignKey('escrow_payment.id'))
    escrow = db.relationship("EscrowPayment", back_populates="order", foreign_keys='EscrowPayment.order_id')
    status = db.Column(db.Enum(StatusEnum, name="status_enum"), default=StatusEnum.pending.value)


    is_escrow = db.Column(db.Boolean, default=True)

    # ✅ Use Enum fields here:
    payment_status = db.Column(
        db.Enum(PaymentStatus, name="payment_status_enum", values_callable=lambda x: [e.value for e in x]),
        nullable=False
    )

    order_status = db.Column(db.String(20), nullable=False, default="initiated")

    from sqlalchemy.dialects.postgresql import ENUM

    status_enum = ENUM(
        'pending', 'success', 'failed',
        name='status_enum',
        create_type=False  # Set to True if you're creating it from SQLAlchemy
    )

    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    buyer = db.relationship("User", back_populates="orders", foreign_keys=[buyer_id])
    seller = db.relationship("User", back_populates="orders_received", foreign_keys=[seller_id])
    agent = db.relationship("User", back_populates="orders_as_agent", foreign_keys=[agent_id])
    product = db.relationship("Product", back_populates="orders")
    reviews = db.relationship('Review', back_populates='order', cascade='all, delete-orphan')

class Payment(db.Model):
    __tablename__ = 'payment'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    reference = db.Column(db.String(100), unique=True, nullable=False)
    plan_name = db.Column(db.String(50), nullable=False)
    amount = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default='pending')
    verified = db.Column(db.Boolean, default=False)
    verified_at = db.Column(db.DateTime, nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    refund_requested = db.Column(db.Boolean, default=False)
    refunded_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', back_populates='payments')

    def set_expiry(self, duration_days):
        self.expires_at = datetime.utcnow() + timedelta(days=duration_days)
from sqlalchemy import Numeric
from decimal import Decimal
class Wallet(db.Model):
    __tablename__ = 'wallet'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)


    promotion_revenue = db.Column(db.Float, default=0.0)
    balance = db.Column(Numeric(precision=12, scale=2, asdecimal=True), default=Decimal("0.00"))
    pending_balance = db.Column(Numeric(precision=12, scale=2, asdecimal=True), default=Decimal("0.00"))
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship("User", back_populates="wallet", uselist=False)
    transactions = db.relationship("WalletTransaction", back_populates="wallet", cascade="all, delete-orphan")

    def current_balance(self):
        return sum(
            txn.amount if txn.transaction_type == 'credit' else -txn.amount
            for txn in self.transactions
            if txn.status == "success"
        )


class WalletTransaction(db.Model):
    __tablename__ = 'wallet_transaction'

    id = db.Column(db.Integer, primary_key=True)

    wallet_id = db.Column(db.Integer, db.ForeignKey('wallet.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    related_escrow_id = db.Column(db.Integer, db.ForeignKey('escrow.id'), nullable=True)

    amount = db.Column(db.Float, nullable=False)
    transaction_type = db.Column(db.String(20))  # 'credit', 'debit', 'escrow_hold', 'escrow_release'
    description = db.Column(db.String(255))

    status = db.Column(db.String(20), default="success")  # pending, success, failed
    reference = db.Column(db.String(100), unique=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    wallet = db.relationship("Wallet", back_populates="transactions")


class PayoutTransaction(db.Model):
    __tablename__ = 'payout_transaction'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    amount = db.Column(db.Integer)
    reference = db.Column(db.String)
    status = db.Column(db.String)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    bank_code = db.Column(db.String(50))
    account_number = db.Column(db.String(20))
    account_name = db.Column(db.String(100))


class AdminRevenue(db.Model):
    __tablename__ = 'admin_revenue'
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Integer)
    source = db.Column(db.String)  # e.g., "escrow"
    reference = db.Column(db.String)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Setting(db.Model):
    __tablename__ = "settings"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.String(255), nullable=True)

    def __repr__(self):
        return f"<Setting {self.key}={self.value}>"





class PromotionPayment(db.Model):
    __tablename__ = 'promotion_payment'
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    promo_type = db.Column(db.String(50))
    days = db.Column(db.Integer)
    price = db.Column(db.Integer)
    reference = db.Column(db.String(100), unique=True)
    status = db.Column(db.String(20), default="pending")  # pending, paid, failed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    paid_at = db.Column(db.DateTime, nullable=True)

    product = db.relationship('Product', backref='promotions')

class PromotionHistory(db.Model):
    __tablename__= 'promotion_history'
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    promo_type = db.Column(db.String(50))  # 'top', 'boost', 'feature'
    reference = db.Column(db.String(100))
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    ends_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ProfitHistory(db.Model):
    __tablename__ = 'profit_history'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    source_type = db.Column(db.String(50))  # 'subscription', 'promotion', 'escrow'
    description = db.Column(db.String(255))  # e.g. 'Pro Plan', 'Top Promo', 'Escrow Fee on Product XYZ'
    amount = db.Column(db.Float, nullable=False)
    reference = db.Column(db.String(100), nullable=True)  # Optional Paystack ref
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship('User', back_populates='profit_history')
    status = db.Column(db.String(20), default="success")
    product = db.relationship("Product")

class PlatformWallet(db.Model):
    __tablename__ = 'platform_wallet'
    id = db.Column(db.Integer, primary_key=True)
    balance = db.Column(db.Float, default=0.0)
    total_earned = db.Column(db.Float, default=0.0)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

# app/models.py
class AdminWalletTransaction(db.Model):
    __tablename__= 'admin_wallet_transaction'
    id = db.Column(db.Integer, primary_key=True)
    amount = db.Column(db.Float, nullable=False)
    type = db.Column(db.String(50))  # 'withdrawal' or 'deposit'
    description = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reference = db.Column(db.String(100), unique=True)


class EscrowPayment(db.Model):
    __tablename__ = 'escrow_payment'

    id = db.Column(db.Integer, primary_key=True)

    buyer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    seller_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=True)
    reference = db.Column(db.String(100), unique=True, nullable=False)
    base_amount = db.Column(db.Float, nullable=False)
    escrow_fee = db.Column(db.Float, nullable=False)
    total_amount = db.Column(db.Float, nullable=False)
    partial_release_amount = db.Column(db.Float, default=0.0)
    amount = db.Column(db.Float, nullable=False)
    offer_amount = db.Column(db.Float, nullable=True)
    status = db.Column(db.String(50), default='pending')  # 'pending', 'paid', 'released'
    paystack_ref = db.Column(db.String(255))
    payment_reference = db.Column(db.String(100), nullable=True)
    is_paid = db.Column(db.Boolean, default=False)
    paid_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)
    total_escrow_balance = db.Column(db.Float, default=0.0)
    buyer_name = db.Column(db.String(100))     # ✅ Add this
    seller_name = db.Column(db.String(100))
    is_disbursed = db.Column(db.Boolean, default=False)
    is_completed = db.Column(db.Boolean, default=False)
    buyer_marked_complete = db.Column(db.Boolean, default=False)
    seller_paid = db.Column(db.Boolean, default=False)
    marked_by_admin = db.Column(db.Boolean, default=False)
    marked_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    released_at = db.Column(db.DateTime, nullable=True)
    agent_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    agent = db.relationship('User', foreign_keys=[agent_id])
    vet_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    assigned_logistics_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    logistics = db.relationship('User', foreign_keys=[assigned_logistics_id])
    order_completed = db.Column(db.Boolean, default=False)
    released_at = db.Column(db.DateTime, nullable=True)
    vet = db.relationship('User', foreign_keys=[vet_id])
    admin_fee = db.Column(db.Integer, default=0)  # fee in naira
    amount_to_seller = db.Column(db.Integer, default=0)  # payout amount
    is_released = db.Column(db.Boolean, default=False, nullable=False)  # funds approved to release
    is_withdrawn = db.Column(db.Boolean, default=False, nullable=False)  # funds a
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=True)
    is_deleted = db.Column(db.Boolean, default=False)
    order = db.relationship("Order", back_populates="escrow", foreign_keys=[order_id])
    provider_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)  # seller
    type = db.Column(db.String, nullable=False, default="product")
    # ✅ Relationships
    buyer = db.relationship('User', back_populates='buyer_escrows', foreign_keys=[buyer_id])
    seller = db.relationship('User', back_populates='seller_escrows', foreign_keys=[seller_id])
    product = db.relationship('Product', backref='escrow_transactions')
    payer = db.relationship("User", foreign_keys=[buyer_id], backref="escrows_paid")
    provider = db.relationship("User", foreign_keys=[provider_id], backref="escrows_received")
    payment_method = db.Column(
        db.Enum('escrow', 'direct', name='logistics_payment_enum'),
        default='escrow',
        nullable=False
    )

    def check_ready(self):
        """Mark escrow ready if both parties completed."""
        if self.completed_by_buyer and self.completed_by_provider:
            self.status = "ready_to_release"
            db.session.commit()

    related_order = db.relationship(
        'Order',
        foreign_keys=[order_id],
        back_populates='escrow'
    )



class BankDetails(db.Model):
    __tablename__ = "bank_details"   # MUST match here and in Withdrawal

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    bank_name = db.Column(db.String(100), nullable=False)
    account_number = db.Column(db.String(20), nullable=False, unique=True)
    account_name = db.Column(db.String(100), nullable=False)
    bank_code = db.Column(db.String(10), nullable=False)
    recipient_code = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship("User", backref="bank_accounts")

# ---------------------- SUBSCRIPTION ----------------------
class Subscription(db.Model):
    __tablename__ = 'subscription'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    plan = db.Column(db.String(20))
    name = db.Column(db.String(100))
    price = db.Column(db.Integer)
    start_date = db.Column(db.DateTime, default=datetime.utcnow)
    end_date = db.Column(db.DateTime)
    payment_method = db.Column(db.String(20))
    verified_badge = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(50))
    plan_name = db.Column(db.String(100), nullable=False)
    duration_days = db.Column(db.Integer, default=30)
    tx_ref = db.Column(db.String(100), unique=True, nullable=True)
    payment_status = db.Column(db.String(20), default='pending')
    reference = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    grace_end = db.Column(db.DateTime, nullable=True)
    upload_limit = db.Column(db.Integer)
    amount = db.Column(db.Float)

    owner = db.relationship(
        'User',
        back_populates='subscription',
        foreign_keys=[user_id]
    )

    creator = db.relationship('User', back_populates='created_subscriptions', foreign_keys=[created_by])

    @property
    def is_active_now(self):
        return self.end_date and datetime.utcnow() <= self.end_date

    def days_remaining(self):
        if self.end_date:
            remaining = (self.end_date - datetime.utcnow()).days
            return max(0, remaining)
        return 0

    def in_grace_period(self):
        now = datetime.utcnow()
        return self.grace_end and self.end_date and self.end_date < now <= self.grace_end

    def is_active(self):
        return self.end_date and datetime.utcnow() <= self.end_date

    def in_grace_period(self):
        now = datetime.utcnow()
        return self.grace_end and self.end_date and self.end_date < now <= self.grace_end

    def is_expired(self):
        return not self.is_active() and not self.in_grace_period()

    def days_left(self):
        now = datetime.utcnow()
        if self.is_active():
            return (self.end_date - now).days
        elif self.in_grace_period():
            return (self.grace_end - now).days
        return 0


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    role = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    state = db.Column(db.String(100), nullable=False)
    city = db.Column(db.String(100), nullable=False)
    street = db.Column(db.String(150), nullable=False)
    phone = db.Column(db.String(15), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    company_name = db.Column(db.String(150))
    about = db.Column(db.Text)
    profile_photo = db.Column(db.String(200))
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    is_verified = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    is_flagged = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    is_available = db.Column(db.Boolean, default=True)
    is_online = db.Column(db.Boolean, default=False)
    bank_code = db.Column(db.String(20), nullable=True)
    bank_account_number = db.Column(db.String(20), nullable=True)
    account_name = db.Column(db.String(100), nullable=True)

    # Subscription fields
    subscription_id = db.Column(db.Integer, db.ForeignKey('subscription.id'))
    subscription_plan = db.Column(db.String, nullable=True)
    subscription_start = db.Column(db.DateTime)
    subscription_end = db.Column(db.DateTime)
    subscription_expiry = db.Column(db.DateTime, nullable=True)
    grace_end = db.Column(db.DateTime)
    plan_expiry = db.Column(db.DateTime)
    plan_expires = db.Column(db.DateTime, nullable=True)
    plan_name = db.Column(db.String(50), default='Free')
    current_plan = db.Column(db.String(50), default='free')
    plan = db.Column(db.String)
    upload_limit = db.Column(db.Integer, default=2)
    recipient_code = db.Column(db.String(100), nullable=True)
    selected_payout_account_id = db.Column(db.Integer, nullable=True)
    bank_name = db.Column(db.String(100))
    account_number = db.Column(db.String(20))
    wallet_balance = db.Column(db.Float, default=0.0)
    profile_picture = db.Column(db.String, nullable=True)
    documents = db.Column(db.ARRAY(db.String), default=[])
    availability_status = db.Column(db.Boolean, default=True)  # or default=False depending on your logic
    from sqlalchemy.dialects.postgresql import ARRAY
    kyc = db.relationship("AgentKYC", back_populates="user", uselist=False)
    verification_documents = db.relationship("VerificationDocument", backref="user")
    service_tags = db.Column(ARRAY(db.String), nullable=True)
    # Relationships
    payments = db.relationship('Payment', foreign_keys='Payment.user_id', back_populates='user')
    wallet = db.relationship("Wallet", back_populates="user", uselist=False)
    payout = db.relationship("PayoutTransaction", backref="user", uselist=False)
    bank_details = db.relationship("BankDetails", back_populates="user", uselist=False)
    profit_history = db.relationship('ProfitHistory', back_populates='user')
    is_escrow = db.Column(db.Boolean, default=False, nullable=False)

    buyer_escrows = db.relationship('EscrowPayment', back_populates='buyer', foreign_keys='EscrowPayment.buyer_id')
    seller_escrows = db.relationship('EscrowPayment', back_populates='seller', foreign_keys='EscrowPayment.seller_id')
    logistics_profile = db.relationship("LogisticsProfile", back_populates="user", uselist=False)

    # Products this user owns (as seller)
    products = db.relationship(
        'Product',
        back_populates='owner',
        foreign_keys='Product.user_id'
    )

    # Products this user is assigned to (as agent)
    assigned_products = db.relationship(
        'Product',
        back_populates='agent',
        foreign_keys='Product.agent_id'
    )

    # Orders
    orders = db.relationship(
        "Order",
        back_populates="buyer",
        foreign_keys=lambda: [Order.buyer_id]
    )
    orders_received = db.relationship(
        "Order",
        back_populates="seller",
        foreign_keys=lambda: [Order.seller_id]
    )
    orders_as_agent = db.relationship(
        "Order",
        back_populates="agent",
        foreign_keys=lambda: [Order.agent_id]
    )

    subscription = db.relationship(
        'Subscription',
        back_populates='owner',
        uselist=False,
        foreign_keys='Subscription.user_id'
    )
    created_subscriptions = db.relationship(
        'Subscription',
        back_populates='creator',
        foreign_keys='Subscription.created_by'
    )

    # In User model
    received_reviews = db.relationship(
        'Review',
        foreign_keys='Review.reviewee_id',
        back_populates='reviewee',
        lazy='dynamic'
    )

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def profile_completion(self):
        # Include all relevant fields for profile completion
        fields = [
            self.first_name,
            self.last_name,
            self.phone,
            self.email,
            self.state,
            self.city,
            self.street,
            self.company_name,
            self.about,
            self.profile_photo
        ]

        # Count filled fields
        filled = sum(1 for f in fields if f and str(f).strip() != "")
        total = len(fields)

        # Add KYC verification as a separate requirement
        total += 1
        if getattr(self, "kyc", None) and getattr(self.kyc, "status", None) == "approved":
            filled += 1

        return int((filled / total) * 100)

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"







class VerificationDocument(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    doc_type = db.Column(db.String(50))  # 'government_id', 'selfie', etc.
    file_path = db.Column(db.String(200))
    status = db.Column(db.String(20), default="pending")  # pending, approved, rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ---------------------- PRODUCT ----------------------
class Product(db.Model):
    __tablename__ = 'products'

    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(100), nullable=False)
    photos = db.Column(MutableList.as_mutable(ARRAY(db.String)), nullable=True)
    state = db.Column(db.String(100), nullable=False)
    city = db.Column(db.String(100), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    type = db.Column(db.String(100), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    description = db.Column(db.Text, nullable=True)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    open_to_negotiation = db.Column(negotiation_enum, nullable=False)
    phone_display = db.Column(db.String(15), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_deleted = db.Column(db.Boolean, default=False)
    views = db.Column(db.Integer, default=0)
    is_featured = db.Column(db.Boolean, default=False)
    boost_score = db.Column(db.Integer, default=0)
    is_flagged = db.Column(db.Boolean, default=False, nullable=False)
    is_boosted = db.Column(db.Boolean, default=False)
    is_top = db.Column(db.Boolean, default=False)
    boost_expiry = db.Column(db.DateTime, nullable=True)
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    is_promoted = db.Column(db.Boolean, default=False)
    promotion_type = db.Column(db.String(50))
    promotion_end_date = db.Column(db.DateTime, nullable=True)
    featured_expiry = db.Column(db.DateTime, nullable=True)
    top_expiry = db.Column(db.DateTime, nullable=True)
    boosted_at = db.Column(db.DateTime, nullable=True)
    last_shown = db.Column(db.DateTime, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    agent_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # Relationship to seller
    owner = db.relationship(
        'User',
        back_populates='products',
        foreign_keys=[user_id]
    )

    # Relationship to agent
    agent = db.relationship(
        'User',
        back_populates='assigned_products',
        foreign_keys=[agent_id]
    )

    orders = db.relationship("Order", back_populates="product")

# ---------------------- MESSAGE ----------------------
class Message(db.Model):
    __tablename__ = 'messages'

    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    seen = db.Column(db.Boolean, default=False)
    seen_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'sender_id': self.sender_id,
            'receiver_id': self.receiver_id,
            'content': self.content,
            'timestamp': self.timestamp.isoformat(),
            'seen': self.seen,
            'seen_at': self.seen_at.strftime('%Y-%m-%d %H:%M:%S') if self.seen_at else None

        }

# ---------------------- AGENT ----------------------
class Agent(db.Model):
    __tablename__ = 'agents'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    specialization = db.Column(db.String(100))
    bio = db.Column(db.Text)
    is_verified = db.Column(db.Boolean, default=False)
    rating = db.Column(db.Float, default=0)
    total_reviews = db.Column(db.Integer, default=0)
    availability = db.Column(db.String(50), default="Available")
    whatsapp_number = db.Column(db.String(20))
    portfolio_photos = db.Column(ARRAY(db.String), nullable=True)
    featured = db.Column(db.Boolean, default=False)

    user = db.relationship('User')

# ---------------------- REVIEW ----------------------
class Review(db.Model):
    __tablename__ = 'reviews'

    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey('booking_requests.id'), nullable=False)
    reviewer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    reviewee_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'), nullable=True)


    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    booking = db.relationship('BookingRequest', back_populates='reviews')
    reviewee = db.relationship('User', foreign_keys=[reviewee_id], back_populates='received_reviews')
    order = db.relationship('Order', back_populates='reviews', foreign_keys=[order_id])
    reviewer = db.relationship('User', foreign_keys=[reviewer_id], backref='given_reviews')


    product = db.relationship('Product', backref='reviews')

class Purchase(db.Model):
    __tablename__ = 'purchases'  # ✅ add this
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    purchased_at = db.Column(db.DateTime, default=datetime.utcnow)


# ---------------------- AGENT PROFILE ----------------------
class AgentProfile(db.Model):
    __tablename__ = 'agent_profiles'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    bio = db.Column(db.Text, nullable=True)
    specialties = db.Column(ARRAY(db.String), nullable=True)
    availability_status = db.Column(availability_enum, default='Available')
    verified = db.Column(db.Boolean, default=False)
    rating = db.Column(db.Float, default=0.0)
    num_reviews = db.Column(db.Integer, default=0)
    whatsapp_link = db.Column(db.String, nullable=True)
    portfolio_links = db.Column(ARRAY(db.String), nullable=True)

    user = db.relationship('User', backref='agent_profile', uselist=False)

# ---------------------- VERIFICATION REQUEST ----------------------
class VerificationRequest(db.Model):
    __tablename__ = 'verification_requests'

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    buyer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    agent_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    agent_report = db.Column(db.Text, nullable=True)
    photo = db.Column(db.String, nullable=True)
    status = db.Column(db.String, default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    product = db.relationship('Product', backref='verification_requests')
    buyer = db.relationship('User', foreign_keys=[buyer_id])
    agent = db.relationship('User', foreign_keys=[agent_id])

# ---------------------- NOTIFICATION ----------------------
class Notification(db.Model):
    __tablename__ = 'notifications'

    id = db.Column(db.Integer, primary_key=True)
    notification_type = db.Column(db.String, nullable=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    title = db.Column(db.String(255))
    link = db.Column(db.String(255))


    message = db.Column(db.Text)
    type = db.Column(db.String(50))
    is_read = db.Column(db.Boolean, default=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    # ✅ Disambiguate relationships
    user = db.relationship('User', foreign_keys=[user_id], backref='notifications_received')
    sender = db.relationship('User', foreign_keys=[sender_id], backref='notifications_sent')

class Inspection(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey('booking_requests.id'), nullable=False)
    inspector_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # who did the inspection
    inspection_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    status = db.Column(db.String(50), nullable=False)  # e.g., 'passed', 'failed', 'pending'
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    inspector = db.relationship('User', foreign_keys=[inspector_id])
    booking = db.relationship('BookingRequest', back_populates='inspection')




class BookingRequest(db.Model):
    __tablename__ = 'booking_requests'

    id = db.Column(db.Integer, primary_key=True)
    buyer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    agent_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.Time, nullable=False)
    reason = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    inspection_report = db.Column(db.Text)
    inspection_outcome = db.Column(db.String(50))
    inspection_reported_at = db.Column(db.DateTime)
    booking_time = db.Column(db.DateTime, nullable=True)
    seller_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    inspection_photos = db.Column(ARRAY(db.String), nullable=True)  # ✅ ARRAY not JSON
    inspection_files = db.Column(ARRAY(db.String), default=[])      # Optional for files
    inspection_seen_by_buyer = db.Column(db.Boolean, default=False)
    inspection_marked_complete = db.Column(db.Boolean, nullable=True)  # True, False, or None
    message = db.Column(db.Text, nullable=True)  # ✅ This must match
    booking_time = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    buyer = db.relationship('User', backref='bookings', foreign_keys=[buyer_id])
    agent = db.relationship('User', foreign_keys=[agent_id])

    product = db.relationship('Product', backref='bookings')


    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=True)
    reviews = db.relationship('Review', back_populates='booking')
    inspection = db.relationship('Inspection', back_populates='booking', uselist=False)

# models.py

# models.py
class InspectionFeedback(db.Model):
    __tablename__ = 'inspection_feedbacks'
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey('booking_requests.id'), nullable=False, unique=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)  # buyer
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Agent reply
    reply = db.Column(db.Text)
    replied_at = db.Column(db.DateTime)

    user = db.relationship('User')
    booking = db.relationship('BookingRequest', backref='inspection_feedbacks')

class ChatMessage(db.Model):
    __tablename__ = 'chat_messages'

    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    message = db.Column(db.Text, nullable=True)
    file_path = db.Column(db.String, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)

    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_messages')
    receiver = db.relationship('User', foreign_keys=[receiver_id], backref='received_messages')





class AdminLog(db.Model):
    __tablename__ = 'admin_logs'

    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    action = db.Column(db.String(255))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


# models/payment.py




class Escrow(db.Model):
    __tablename__ = 'escrow'

    id = db.Column(db.Integer, primary_key=True)

    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    buyer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    agent_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    logistics_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    agent_booking_id = db.Column(db.Integer, db.ForeignKey('booking_requests.id'), nullable=True)
    logistics_booking_id = db.Column(db.Integer, db.ForeignKey('logistics_booking.id'), nullable=True)

    agreed_amount = db.Column(db.Numeric(10, 2), nullable=False)         # Amount without fee
    escrow_fee = db.Column(db.Numeric(10, 2), nullable=False)           # Platform fee
    total_paid = db.Column(db.Numeric(10, 2), nullable=False)           # Total amount (agreed + fee)

    is_paid = db.Column(db.Boolean, default=False)
    is_released = db.Column(db.Boolean, default=False)
    release_to_agent = db.Column(db.Boolean, default=False)
    release_to_logistics = db.Column(db.Boolean, default=False)

    status = db.Column(db.String(20), default='pending')                # pending, completed, cancelled

    payment_reference = db.Column(db.String(100), unique=True)
    released_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)



class RefundLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    payment_id = db.Column(db.Integer, db.ForeignKey('payment.id'), nullable=False)
    admin_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    refunded_at = db.Column(db.DateTime, default=datetime.utcnow)

    admin = db.relationship('User', foreign_keys=[admin_id])
    payment = db.relationship('Payment')

class SubscriptionPlan(db.Model):
    __tablename__ = 'subscription_plans'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False, unique=True)
    price = db.Column(db.Integer, nullable=False)  # In kobo (₦100 = 10000)
    upload_limit = db.Column(db.Integer, nullable=True)  # Use a high number or NULL for unlimited
    boost_score = db.Column(db.Integer, default=0)
    featured = db.Column(db.Boolean, default=False)
    duration_days = db.Column(db.Integer, default=30)  # e.g. 30, 60, etc.
    description = db.Column(db.String(255), nullable=True)
    product_limit = db.Column(db.Integer, nullable=False, default=5)

    def __repr__(self):
        return f'<SubscriptionPlan {self.name}>'


class Wishlist(db.Model):
    __tablename__ = "wishlist"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref="wishlist_items")
    product = db.relationship("Product", backref="wishlisted_by")

class ProductReview(db.Model):
    __tablename__ = 'product_review'
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'), nullable=False)
    reviewer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)  # Should be between 1 and 5
    comment = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    reviewer = db.relationship('User', backref='product_reviews')
    product = db.relationship('Product', backref='product_reviews')  # <- renamed from 'reviews'


    __table_args__ = (
        db.UniqueConstraint('product_id', 'reviewer_id', name='unique_product_reviewer'),
    )

class LogisticsProfile(db.Model):
    __tablename__ = 'logistics_profile'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    company_name = db.Column(db.String(100))
    service_areas = db.Column(db.String)  # e.g., comma-separated or JSON
    vehicle_type = db.Column(db.String(50))
    capacity = db.Column(db.String(50))
    rate_per_km = db.Column(db.Float)
    available = db.Column(db.Boolean, default=True)
    phone = db.Column(db.String(20))
    whatsapp = db.Column(db.String(20))
    sender_name = db.Column(db.String(100))  # add this
    user = db.relationship("User", back_populates="logistics_profile")



from sqlalchemy import Enum

class LogisticsBooking(db.Model):
    __tablename__ = 'logistics_booking'

    id = db.Column(db.Integer, primary_key=True)
    buyer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    requester_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    logistics_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    product_id = db.Column(db.Integer, db.ForeignKey('products.id'))

    pickup_address = db.Column(db.String)
    delivery_address = db.Column(db.String)
    distance_km = db.Column(db.Float)
    estimated_cost = db.Column(db.Float)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # 🚀 Add this field
    payment_method = db.Column(
        Enum('escrow', 'direct', name='logistics_payment_enum'),
        default='escrow',
        nullable=False
    )

    status = db.Column(
        Enum('pending', 'accepted', 'rejected', 'completed', name='booking_status_enum'),
        default='pending'
    )

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    sender_name = db.Column(db.String(100))  # add this
    logistics = db.relationship('User', foreign_keys=[logistics_id], backref='logistics_bookings')
    buyer = db.relationship('User', foreign_keys=[buyer_id])
    product = db.relationship('Product')



class ServiceEscrow(db.Model):
    __tablename__ = 'service_escrow'

    id = db.Column(db.Integer, primary_key=True)
    buyer_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    provider_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    booking_id = db.Column(db.Integer, db.ForeignKey('booking_requests.id'), nullable=True)  # ✅ match table name
    amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(50), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    buyer = db.relationship('User', foreign_keys=[buyer_id])
    provider = db.relationship('User', foreign_keys=[provider_id])
    booking = db.relationship('BookingRequest', backref='escrow', uselist=False)  # ✅ correct class name

class FundTransfer(db.Model):
    __tablename__ = 'fund_transfers'

    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    recipient_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    type = db.Column(db.String(50), nullable=False)
    # ⚡ Explicitly specify foreign_keys for each relationship
    sender = db.relationship(
        'User',
        foreign_keys=[sender_id],
        backref=db.backref('sent_transfers', lazy='dynamic')
    )
    recipient = db.relationship(
        'User',
        foreign_keys=[recipient_id],
        backref=db.backref('received_transfers', lazy='dynamic')
    )

    def __repr__(self):
        return f"<FundTransfer {self.id}: {self.sender_id} → {self.recipient_id} | ₦{self.amount}>"

class EscrowAudit(db.Model):
    __tablename__ = "escrow_audit"
    id = db.Column(db.Integer, primary_key=True)
    escrow_id = db.Column(db.Integer, db.ForeignKey("escrow_payment.id"))
    action = db.Column(db.String(50))  # e.g., "created", "partial_release", "released"
    amount = db.Column(db.Float)
    performed_by = db.Column(db.Integer, db.ForeignKey("users.id"))  # who did the action
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


class AgentKYC(db.Model):
    __tablename__ = "agent_kyc"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    address = db.Column(db.String(255), nullable=False)
    document_type = db.Column(db.String(50), nullable=False)
    document_images = db.Column(db.ARRAY(db.String), nullable=True)  # store uploaded images
    status = db.Column(db.String(20), default="pending")
    # values: "pending", "approved", "rejected"
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship("User", back_populates="kyc")

class Expense(db.Model):
    __tablename__ = 'expense'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(200))
    amount = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(50))

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date = db.Column(db.Date, default=date.today, nullable=False)
    type = db.Column(db.String(10), nullable=False)  # 'Income' or 'Expense'
    category = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(200))
    amount = db.Column(db.Float, nullable=False)
    payment_method = db.Column(db.String(50))
    receipt = db.Column(db.String(200))  # optional file path

    # NEW fields for recurring transactions
    is_recurring = db.Column(db.Boolean, default=False)
    recurring_interval = db.Column(db.String(20))  # e.g., 'weekly', 'monthly', 'yearly'
    next_occurrence = db.Column(db.Date)  # optional, next due date

class Inventory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), nullable=True)
    quantity = db.Column(db.Integer, default=0)
    price = db.Column(db.Float, default=0.0)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Withdrawal(db.Model):
    __tablename__ = "withdrawals"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    bank_id = db.Column(db.Integer, db.ForeignKey("bank_details.id"), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    status = db.Column(db.String(20), default="pending")  # pending/approved/rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    requested_at = db.Column(db.DateTime, default=db.func.now())
    # Relationships
    user = db.relationship("User", backref="withdrawals")
    bank = db.relationship("BankDetails", backref="withdrawals", foreign_keys=[bank_id])
