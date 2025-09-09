from flask_wtf import FlaskForm
from wtforms import TextAreaField, DateTimeLocalField, SubmitField
from wtforms.validators import DataRequired
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired
from wtforms import DateField, TimeField, BooleanField,TextAreaField, SubmitField,SelectField,HiddenField,DecimalField
from wtforms.validators import DataRequired, Email, EqualTo, Length
from flask_wtf import FlaskForm
from wtforms import HiddenField, DecimalField, SubmitField
from wtforms.validators import DataRequired,Optional


class BookProductForm(FlaskForm):
    date = DateField('Date', format='%Y-%m-%d', validators=[DataRequired()])
    time = TimeField('Time', format='%H:%M', validators=[DataRequired()])
    reason = TextAreaField('Booking Message', validators=[DataRequired()])
    submit = SubmitField('Book')



class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

from flask_wtf import FlaskForm
from wtforms import TextAreaField, IntegerField, SubmitField
from wtforms.validators import DataRequired, NumberRange

class FeedbackForm(FlaskForm):
    rating = IntegerField('Rating (1-5)', validators=[DataRequired(), NumberRange(min=1, max=5)])
    comment = TextAreaField('Feedback', validators=[DataRequired()])
    submit = SubmitField('Submit Feedback')

# forms.py
class FeedbackReplyForm(FlaskForm):
    reply = TextAreaField('Reply to Feedback', validators=[DataRequired()])
    submit = SubmitField('Send Reply')
class InspectionForm(FlaskForm):
    notes = TextAreaField('Inspection Notes', validators=[DataRequired()])
    status = SelectField('Status', choices=[('passed', 'Passed'), ('failed', 'Failed')])
    submit = SubmitField('Submit Inspection')

class BookingForm(FlaskForm):
    product_id = HiddenField(validators=[DataRequired()])
    date = DateField('Booking Date', format='%Y-%m-%d', validators=[DataRequired()])
    message = TextAreaField('Message', validators=[DataRequired()])
    submit = SubmitField('Send Booking Request')

class RegistrationForm(FlaskForm):
    first_name = StringField("First Name", validators=[DataRequired()])
    last_name = StringField("Last Name", validators=[DataRequired()])
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField("Confirm Password", validators=[EqualTo('password')])
    submit = SubmitField("Register")

class EscrowPaymentForm(FlaskForm):
    product_id = HiddenField(validators=[DataRequired()])
    amount = DecimalField("Amount", validators=[DataRequired()])
    description = StringField("Description")  # ✅ Add this line
    submit = SubmitField("Proceed to Pay")

class SubscriptionForm(FlaskForm):
    plan = SelectField(
        'Choose Plan',
        choices=[
            ('monthly', 'Monthly ₦1000'),
            ('yearly', 'Yearly ₦10000')
        ],
        validators=[DataRequired()]
    )
    submit = SubmitField('Subscribe Now')

from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, DecimalField, IntegerField, SelectField, SubmitField, MultipleFileField
from wtforms.validators import DataRequired, Length, NumberRange
from flask_wtf.file import FileAllowed

NIGERIAN_STATES = [
    "Abia", "Adamawa", "Akwa Ibom", "Anambra", "Bauchi", "Bayelsa", "Benue", "Borno",
    "Cross River", "Delta", "Ebonyi", "Edo", "Ekiti", "Enugu", "FCT - Abuja", "Gombe", "Imo",
    "Jigawa", "Kaduna", "Kano", "Katsina", "Kebbi", "Kogi", "Kwara", "Lagos", "Nasarawa",
    "Niger", "Ogun", "Ondo", "Osun", "Oyo", "Plateau", "Rivers", "Sokoto", "Taraba",
    "Yobe", "Zamfara"
]

NEGOTIATION_CHOICES = [
    ('Yes', 'Yes'),
    ('No', 'No'),
    ('Not sure', 'Not sure')
]

PRODUCT_TYPES = [
    ('Fresh', 'Fresh'),
    ('Processed', 'Processed'),
    ('Live', 'Live'),
    ('Frozen', 'Frozen')
]

CATEGORIES = [
    ('Cattle', 'Cattle'),
    ('Goat', 'Goat'),
    ('Chicken', 'Chicken'),
    ('Feed', 'Feed'),
    ('Others', 'Others'),
    # Add more as needed
]

class ProductUploadForm(FlaskForm):
    category = SelectField("Category", choices=CATEGORIES, validators=[DataRequired()])
    photos = MultipleFileField("Product Photos", validators=[
        FileAllowed(['jpg', 'jpeg', 'png'], "Only image files are allowed.")
    ])
    state = SelectField("State", choices=[(state, state) for state in NIGERIAN_STATES], validators=[DataRequired()])
    city = StringField("City (LGA)", validators=[DataRequired(), Length(max=100)])
    title = StringField("Product Title", validators=[DataRequired(), Length(max=150)])
    type = SelectField("Type", choices=PRODUCT_TYPES, validators=[DataRequired()])
    quantity = IntegerField("Quantity", validators=[DataRequired(), NumberRange(min=1)])
    description = TextAreaField("Description", validators=[DataRequired(), Length(min=10)])
    price = DecimalField("Price (₦)", validators=[DataRequired()], places=2)
    open_to_negotiation = SelectField("Open to Negotiation?", choices=NEGOTIATION_CHOICES, validators=[DataRequired()])
    submit = SubmitField("Upload Product")
class EscrowPaymentForm(FlaskForm):
    amount = DecimalField('Enter Amount You Wish to Pay', validators=[
        DataRequired(),
        NumberRange(min=0.01, message="Amount must be greater than 0")
    ])
    submit = SubmitField('Proceed to Pay')


class PayoutForm(FlaskForm):
    bank_name = SelectField("Bank", choices=[], validators=[DataRequired()])
    account_number = StringField("Account Number", validators=[DataRequired(), Length(min=10, max=10)])
    account_name = StringField("Account Name", render_kw={'readonly': True})
    recipient_code = StringField("Recipient Code", render_kw={'readonly': True})
    submit = SubmitField("Save Account Details")


class BankDetailsForm(FlaskForm):
    bank_name = SelectField("Bank", choices=[], validators=[DataRequired()])
    account_number = StringField("Account Number", validators=[DataRequired(), Length(min=10, max=10)])
    account_name = StringField("Account Name", render_kw={"readonly": True})
    recipient_code = StringField("Recipient Code", render_kw={"readonly": True})
    submit = SubmitField("Save")

class OfferForm(FlaskForm):
    offer_amount = DecimalField(
        "Offer Amount",
        validators=[DataRequired(message="Offer amount is required and must be a number."),
                    NumberRange(min=1, message="Offer must be at least 1")],
        places=2
    )
    submit = SubmitField("Submit Offer")


class OfferAmountForm(FlaskForm):
    quantity = IntegerField("Quantity", validators=[DataRequired(), NumberRange(min=1)])
    agreed_price = DecimalField("Agreed Price", validators=[DataRequired()])
    total_amount = DecimalField("Total Amount", validators=[DataRequired()])
    notes = TextAreaField("Notes (Optional)")
    submit = SubmitField("Submit Offer")


class WithdrawalForm(FlaskForm):
    bank_account = SelectField("Select Bank Account", choices=[], coerce=int, validators=[DataRequired()])
    amount = DecimalField("Amount", validators=[DataRequired()])
    submit = SubmitField("Withdraw")

class WithdrawalFormSelect(FlaskForm):
    amount = DecimalField("Amount (₦)", validators=[
        DataRequired(message="Enter an amount to withdraw."),
        NumberRange(min=100, message="Minimum withdrawal is ₦100.")
    ])
    submit = SubmitField("Withdraw")

class UsePayoutAccountForm(FlaskForm):
    payout_account = SelectField("Select Payout Account", choices=[], validators=[DataRequired()])
    submit = SubmitField("Use This Account")

class PromoteProductForm(FlaskForm):
    promotion_type = SelectField(
        "Promotion Type",
        choices=[('featured', 'Featured'), ('boosted', 'Boosted'), ('top', 'Top')],
        validators=[DataRequired()]
    )
    submit = SubmitField("Promote Product")

class PromotionForm(FlaskForm):
    promo_type = SelectField(
        "Promotion Type",
        choices=[("featured", "Featured"), ("boosted", "Boosted"), ("top", "Top")],
        validators=[DataRequired()]
    )

    days = SelectField(
        "Duration",
        choices=[("7", "7 Days"), ("30", "30 Days"), ("60", "60 Days")],
        validators=[DataRequired()]
    )

    submit = SubmitField("Promote Product")

class AdminWithdrawalForm(FlaskForm):
    amount = DecimalField("Amount", validators=[DataRequired()])
    bank_name = StringField("Bank", validators=[DataRequired()])
    bank_code = StringField("Bank Code", validators=[DataRequired()])
    account_number = StringField("Account Number", validators=[DataRequired()])
    account_name = StringField("Account Name", validators=[DataRequired()])
    submit = SubmitField("Withdraw")


class CreateOrderForm(FlaskForm):
    quantity = IntegerField("Quantity", validators=[DataRequired(), NumberRange(min=1)])
    agreed_price = DecimalField("Agreed Price per Unit", validators=[DataRequired()], places=2)
    is_escrow = BooleanField("Use Escrow (recommended)", default=True)
    notes = TextAreaField("Additional Notes (optional)")
    submit = SubmitField("Create Order")

# app/agents/forms.py
from flask_wtf import FlaskForm
from wtforms import FileField, SubmitField
from flask_wtf.file import FileAllowed, FileRequired

# app/agents/forms.py
from flask_wtf import FlaskForm
from wtforms import MultipleFileField, SubmitField
from flask_wtf.file import FileAllowed, FileRequired

from flask_wtf import FlaskForm
from wtforms import StringField, SelectField, MultipleFileField, SubmitField
from wtforms.validators import DataRequired, Optional
from flask_wtf.file import FileAllowed

class DocumentUploadForm(FlaskForm):
    full_name = StringField(
        "Full Name",
        validators=[DataRequired(), Length(min=3, max=100)]
    )

    address = TextAreaField(
        "Address",
        validators=[DataRequired(), Length(min=5, max=255)]
    )

    document_type = SelectField(
        "Type of Document",
        choices=[
            ("nin", "NIN"),
            ("drivers_license", "Driver’s License"),
            ("passport", "International Passport"),
        ],
        validators=[DataRequired()]
    )

    documents = MultipleFileField(
        "Upload Supporting Documents (Optional)",
        validators=[
            FileAllowed(['jpg', 'jpeg', 'png', 'pdf'], "Images or PDFs only!")
        ]
    )

    submit = SubmitField("Submit KYC")


class EditProfileForm(FlaskForm):
    first_name = StringField("First Name", validators=[DataRequired()])
    last_name = StringField("Last Name", validators=[DataRequired()])
    about = TextAreaField("About", validators=[Optional()])
    profile_photo = FileField("Profile Photo", validators=[Optional()])
    company_name = StringField("Company Name", validators=[Optional()])
    submit = SubmitField("Save Changes")

class RequestResetForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    submit = SubmitField('Request Password Reset')