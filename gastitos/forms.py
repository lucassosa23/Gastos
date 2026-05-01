from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.core.exceptions import ValidationError
from datetime import date, timedelta
import re
from .models import Gasto, PerfilUsuario, GastoFijo, Vencimiento
from .utils import validate_image_upload, randomize_filename

class GastoForm(forms.ModelForm):
    class Meta:
        model = Gasto
        fields = ['descripcion', 'monto']
        widgets = {
            'descripcion': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Descripción del gasto'}),
            'monto': forms.NumberInput(attrs={
                'class': 'form-control', 
                'step': '0.01', 
                'placeholder': '0.00',
                'style': '-webkit-appearance: textfield; -moz-appearance: textfield;',
                'onkeypress': 'return event.charCode >= 48 && event.charCode <= 57 || event.charCode == 46',
                'oninput': 'this.value = this.value.replace(/[^0-9.]/g, ""); if(this.value < 0) this.value = Math.abs(this.value);'
            }),
        }

class GastoFijoForm(forms.ModelForm):
    class Meta:
        model = GastoFijo
        fields = ['descripcion', 'monto']
        widgets = {
            'descripcion': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Descripción del gasto fijo'}),
            'monto': forms.NumberInput(attrs={
                'class': 'form-control', 
                'step': '0.01', 
                'placeholder': '0.00',
                'style': '-webkit-appearance: textfield; -moz-appearance: textfield;',
                'onkeypress': 'return event.charCode >= 48 && event.charCode <= 57 || event.charCode == 46',
                'oninput': 'this.value = this.value.replace(/[^0-9.]/g, ""); if(this.value < 0) this.value = Math.abs(this.value);'
            }),
        }

class PerfilUsuarioForm(forms.ModelForm):
    first_name = forms.CharField(
        max_length=50, 
        required=False, 
        label='Nombre',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Tu nombre'})
    )
    last_name = forms.CharField(
        max_length=50, 
        required=False, 
        label='Apellido',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Tu apellido'})
    )
    email = forms.EmailField(
        required=False, 
        label='Email',
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'tu@email.com'})
    )
    
    class Meta:
        model = PerfilUsuario
        fields = ['foto', 'telefono', 'fecha_nacimiento', 'profesion']
        widgets = {
            'fecha_nacimiento': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'telefono': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: +56912345678'}),
            'profesion': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Tu profesión'}),
            'foto': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.user:
            self.fields['first_name'].initial = self.instance.user.first_name
            self.fields['last_name'].initial = self.instance.user.last_name
            self.fields['email'].initial = self.instance.user.email

    def clean_foto(self):
        # Solo se valida cuando hay un archivo nuevo (UploadedFile expone
        # content_type). Si el usuario edita el perfil sin tocar la foto,
        # el campo trae la ImageFieldFile existente y no necesita
        # validacion ni renombrado.
        foto = self.cleaned_data.get('foto')
        if foto and hasattr(foto, 'content_type'):
            validate_image_upload(foto)
            randomize_filename(foto)
        return foto
    
    def clean_first_name(self):
        first_name = self.cleaned_data.get('first_name')
        if first_name:
            # Solo letras, espacios y acentos
            if not re.match(r'^[a-zA-ZáéíóúÁÉÍÓÚñÑ\s]+$', first_name):
                raise ValidationError('El nombre solo puede contener letras y espacios.')
            if len(first_name.strip()) < 2:
                raise ValidationError('El nombre debe tener al menos 2 caracteres.')
            if len(first_name.strip()) > 50:
                raise ValidationError('El nombre no puede tener más de 50 caracteres.')
        return first_name.strip() if first_name else first_name
    
    def clean_last_name(self):
        last_name = self.cleaned_data.get('last_name')
        if last_name:
            # Solo letras, espacios y acentos
            if not re.match(r'^[a-zA-ZáéíóúÁÉÍÓÚñÑ\s]+$', last_name):
                raise ValidationError('El apellido solo puede contener letras y espacios.')
            if len(last_name.strip()) < 2:
                raise ValidationError('El apellido debe tener al menos 2 caracteres.')
            if len(last_name.strip()) > 50:
                raise ValidationError('El apellido no puede tener más de 50 caracteres.')
        return last_name.strip() if last_name else last_name
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email:
            # Validación adicional de email
            if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
                raise ValidationError('Ingresa un email válido.')
            # Verificar que no esté en uso por otro usuario
            if self.instance and self.instance.user:
                existing_user = User.objects.filter(email=email).exclude(id=self.instance.user.id).first()
            else:
                existing_user = User.objects.filter(email=email).first()
            if existing_user:
                raise ValidationError('Este email ya está en uso por otro usuario.')
        return email
    
    def clean_telefono(self):
        telefono = self.cleaned_data.get('telefono')
        if telefono:
            # Remover espacios y caracteres especiales para validación
            telefono_clean = re.sub(r'[\s\-\(\)\+]', '', telefono)
            
            # Validar que solo contenga números después de limpiar
            if not telefono_clean.isdigit():
                raise ValidationError('El teléfono solo puede contener números.')
            
            # Para números chilenos: exactamente 9 dígitos (sin código de país)
            if len(telefono_clean) != 9:
                raise ValidationError('El teléfono debe tener exactamente 9 dígitos (ej: 912345678).')
            
            # Debe empezar con 9 para celulares chilenos
            if not telefono_clean.startswith('9'):
                raise ValidationError('El número de celular debe empezar con 9.')
        
        return telefono
    
    def clean_fecha_nacimiento(self):
        fecha_nacimiento = self.cleaned_data.get('fecha_nacimiento')
        if fecha_nacimiento:
            today = date.today()
            
            # No puede ser fecha futura
            if fecha_nacimiento > today:
                raise ValidationError('La fecha de nacimiento no puede ser en el futuro.')
            
            # Debe ser mayor de 15 años (edad mínima razonable)
            min_age_date = today - timedelta(days=15*365)
            if fecha_nacimiento > min_age_date:
                raise ValidationError('Debes tener al menos 15 años para usar esta aplicación.')
            
            # No puede ser mayor de 120 años
            max_age_date = today - timedelta(days=120*365)
            if fecha_nacimiento < max_age_date:
                raise ValidationError('La fecha de nacimiento no puede ser anterior a 120 años.')
        
        return fecha_nacimiento
    
    def save(self, commit=True):
        perfil = super().save(commit=False)
        if commit:
            perfil.save()
            # Actualizar datos del usuario
            user = perfil.user
            user.first_name = self.cleaned_data['first_name']
            user.last_name = self.cleaned_data['last_name']
            user.email = self.cleaned_data['email']
            user.save()
        return perfil

class SalarioForm(forms.ModelForm):
    class Meta:
        model = PerfilUsuario
        fields = ['salario_mensual']
        widgets = {
            'salario_mensual': forms.NumberInput(attrs={
                'class': 'form-control', 
                'step': '0.01', 
                'placeholder': 'Ingresa tu salario',
                'style': '-webkit-appearance: textfield; -moz-appearance: textfield;',
                'onkeypress': 'return event.charCode >= 48 && event.charCode <= 57 || event.charCode == 46',
                'oninput': 'this.value = this.value.replace(/[^0-9.]/g, ""); if(this.value < 0) this.value = Math.abs(this.value);'
            })
        }

class RegistroForm(UserCreationForm):
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'tu@email.com'}))

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({'class': 'form-control', 'placeholder': 'Nombre de usuario'})
        self.fields['password1'].widget.attrs.update({'class': 'form-control', 'placeholder': 'Contraseña'})
        self.fields['password2'].widget.attrs.update({'class': 'form-control', 'placeholder': 'Confirmar contraseña'})
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data.get('email')
        if commit:
            user.save()
        return user

class VencimientoForm(forms.ModelForm):
    class Meta:
        model = Vencimiento
        fields = ['descripcion', 'fecha_vencimiento', 'activo']
        widgets = {
            'descripcion': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Ej: Pago de tarjeta de crédito, Renovación de seguro'
            }),
            'fecha_vencimiento': forms.DateInput(attrs={
                'type': 'date', 
                'class': 'form-control'
            }),
            'activo': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            })
        }
        labels = {
            'descripcion': 'Descripción del vencimiento',
            'fecha_vencimiento': 'Fecha de vencimiento',
            'activo': 'Activo (mostrar advertencias)'
        }
    
    def clean_fecha_vencimiento(self):
        fecha = self.cleaned_data.get('fecha_vencimiento')
        if fecha:
            # Verificar que la fecha no sea en el pasado (permitir hoy)
            if fecha < date.today():
                raise ValidationError('La fecha de vencimiento no puede ser en el pasado.')
        return fecha

class BootstrapAuthenticationForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({'class': 'form-control', 'placeholder': 'Usuario'})
        self.fields['password'].widget.attrs.update({'class': 'form-control', 'placeholder': 'Contraseña'})