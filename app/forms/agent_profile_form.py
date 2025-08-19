# app/forms/agent_profile_form.py

from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, BooleanField, FieldList
from wtforms.validators import DataRequired

class AgentProfileForm(FlaskForm):
    bio = TextAreaField('Bio')
    specialties = StringField('Specialties (comma-separated)')
    availability_status = SelectField('Availability', choices=[('Available', 'Available'), ('Busy', 'Busy'), ('Away', 'Away')])
    whatsapp_link = StringField('WhatsApp Link')
    portfolio_links = StringField('Portfolio Links (comma-separated)')
    verified = BooleanField('Verified Agent')
