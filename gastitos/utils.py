import re
import cv2
import numpy as np
from PIL import Image
import pytesseract
import uuid
from datetime import datetime, date
from decimal import Decimal, InvalidOperation
import os
from django.core.exceptions import ValidationError


# ============================================================================
# Validacion de uploads
# ============================================================================

# Limites configurables. Si crece la app, mover a settings.
MAX_IMAGE_SIZE = 5 * 1024 * 1024   # 5 MB
MAX_PDF_SIZE = 10 * 1024 * 1024    # 10 MB

ALLOWED_IMAGE_CONTENT_TYPES = {
    'image/jpeg', 'image/png', 'image/webp', 'image/heic',
}
ALLOWED_IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.heic'}
ALLOWED_PDF_CONTENT_TYPES = {'application/pdf'}
ALLOWED_PDF_EXTENSIONS = {'.pdf'}


def _validate_upload(uploaded_file, *, max_size, allowed_content_types,
                     allowed_extensions, kind_label):
    """Valida un archivo subido. Levanta ValidationError si no cumple."""
    if uploaded_file.size > max_size:
        raise ValidationError(
            f'{kind_label} excede el tamaño máximo permitido '
            f'({max_size // (1024 * 1024)} MB).'
        )

    content_type = (uploaded_file.content_type or '').lower()
    if content_type not in allowed_content_types:
        raise ValidationError(f'{kind_label}: tipo de archivo no permitido.')

    name = (uploaded_file.name or '').lower()
    if not any(name.endswith(ext) for ext in allowed_extensions):
        raise ValidationError(f'{kind_label}: extensión no permitida.')


def validate_image_upload(uploaded_file):
    """Valida una imagen subida (jpeg/png/webp/heic, max 5 MB)."""
    _validate_upload(
        uploaded_file,
        max_size=MAX_IMAGE_SIZE,
        allowed_content_types=ALLOWED_IMAGE_CONTENT_TYPES,
        allowed_extensions=ALLOWED_IMAGE_EXTENSIONS,
        kind_label='Imagen',
    )


def validate_pdf_upload(uploaded_file):
    """Valida un PDF subido (application/pdf, max 10 MB)."""
    _validate_upload(
        uploaded_file,
        max_size=MAX_PDF_SIZE,
        allowed_content_types=ALLOWED_PDF_CONTENT_TYPES,
        allowed_extensions=ALLOWED_PDF_EXTENSIONS,
        kind_label='PDF',
    )


def randomize_filename(uploaded_file):
    """Reemplaza el nombre del archivo por uuid4 + extensión original.

    Mitiga revelacion del nombre original del cliente y evita pisado entre
    usuarios cuando varios suben archivos con el mismo nombre.
    """
    _, ext = os.path.splitext(uploaded_file.name or '')
    uploaded_file.name = f'{uuid.uuid4().hex}{ext.lower()}'

# Configurar la ruta de Tesseract para Windows
if os.name == 'nt':  # Windows
    tesseract_path = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
    if os.path.exists(tesseract_path):
        pytesseract.pytesseract.tesseract_cmd = tesseract_path
    else:
        # Intentar rutas alternativas
        possible_paths = [
            r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
            r'C:\Users\{}\AppData\Local\Tesseract-OCR\tesseract.exe'.format(os.getenv('USERNAME')),
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                pytesseract.pytesseract.tesseract_cmd = path
                break

def procesar_imagen_comprobante(imagen_path):
    """
    Procesa una imagen de comprobante para extraer monto y fecha usando OCR.
    
    Args:
        imagen_path: Ruta de la imagen a procesar
        
    Returns:
        dict: Diccionario con 'monto' y 'fecha' extraídos, o None si no se encuentra
    """
    try:
        # Verificar si Tesseract está disponible
        if not hasattr(pytesseract.pytesseract, 'tesseract_cmd') or not pytesseract.pytesseract.tesseract_cmd:
            print("Tesseract no está configurado correctamente")
            return None
            
        # Abrir y procesar la imagen
        imagen = cv2.imread(imagen_path)
        if imagen is None:
            return None
            
        # Convertir a escala de grises
        gris = cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY)
        
        # Aplicar filtros para mejorar la legibilidad
        # Reducir ruido
        gris = cv2.medianBlur(gris, 3)
        
        # Mejorar contraste
        gris = cv2.convertScaleAbs(gris, alpha=1.5, beta=30)
        
        # Binarización adaptativa
        binario = cv2.adaptiveThreshold(gris, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
        
        # Convertir a PIL Image para pytesseract
        pil_imagen = Image.fromarray(binario)
        
        # Extraer texto usando OCR
        try:
            # Intentar primero con español, luego con inglés si falla
            try:
                texto = pytesseract.image_to_string(pil_imagen, lang='spa')
            except:
                # Si falla el español, usar inglés por defecto
                texto = pytesseract.image_to_string(pil_imagen, lang='eng')
        except pytesseract.TesseractNotFoundError:
            print("Tesseract no encontrado. Por favor instale Tesseract OCR.")
            return None
        except Exception as ocr_error:
            print(f"Error en OCR: {ocr_error}")
            # Último intento sin especificar idioma
            try:
                texto = pytesseract.image_to_string(pil_imagen)
            except:
                return None
        
        # Procesar el texto extraído
        resultado = extraer_datos_texto(texto)
        
        return resultado
        
    except Exception as e:
        print(f"Error procesando imagen: {e}")
        return None

def extraer_datos_texto(texto):
    """
    Extrae monto y fecha del texto OCR.
    
    Args:
        texto: Texto extraído por OCR
        
    Returns:
        dict: Diccionario con 'monto' y 'fecha' extraídos
    """
    resultado = {'monto': None, 'fecha': None}
    
    # Limpiar texto
    texto = texto.replace('\n', ' ').replace('\r', ' ')
    
    # Patrones para buscar montos
    patrones_monto = [
        r'\$\s*([0-9]{1,3}(?:[.,][0-9]{3})*(?:[.,][0-9]{2})?)',  # $1.234,56 o $1,234.56
        r'([0-9]{1,3}(?:[.,][0-9]{3})*(?:[.,][0-9]{2})?)\s*\$',  # 1.234,56$ o 1,234.56$
        r'total[:\s]*\$?\s*([0-9]{1,3}(?:[.,][0-9]{3})*(?:[.,][0-9]{2})?)',  # Total: $1.234,56
        r'importe[:\s]*\$?\s*([0-9]{1,3}(?:[.,][0-9]{3})*(?:[.,][0-9]{2})?)',  # Importe: $1.234,56
        r'monto[:\s]*\$?\s*([0-9]{1,3}(?:[.,][0-9]{3})*(?:[.,][0-9]{2})?)',  # Monto: $1.234,56
    ]
    
    # Buscar monto
    for patron in patrones_monto:
        match = re.search(patron, texto, re.IGNORECASE)
        if match:
            monto_str = match.group(1)
            try:
                # Normalizar formato de número (convertir comas a puntos para decimales)
                if ',' in monto_str and '.' in monto_str:
                    # Formato 1.234,56 (europeo)
                    if monto_str.rfind(',') > monto_str.rfind('.'):
                        monto_str = monto_str.replace('.', '').replace(',', '.')
                    # Formato 1,234.56 (americano)
                    else:
                        monto_str = monto_str.replace(',', '')
                elif ',' in monto_str:
                    # Solo comas - asumir formato europeo si hay más de 2 dígitos después
                    if len(monto_str.split(',')[-1]) == 2:
                        monto_str = monto_str.replace(',', '.')
                    else:
                        monto_str = monto_str.replace(',', '')
                
                resultado['monto'] = float(monto_str)
                break
            except (ValueError, InvalidOperation):
                continue
    
    # Patrones para buscar fechas
    patrones_fecha = [
        r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})',  # DD/MM/YYYY o DD-MM-YYYY
        r'(\d{1,2})[/-](\d{1,2})[/-](\d{2})',  # DD/MM/YY o DD-MM-YY
        r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})',  # YYYY/MM/DD o YYYY-MM-DD
        r'(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})',  # 15 de enero de 2024
    ]
    
    meses = {
        'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4,
        'mayo': 5, 'junio': 6, 'julio': 7, 'agosto': 8,
        'septiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12
    }
    
    # Buscar fecha
    for patron in patrones_fecha:
        matches = re.findall(patron, texto, re.IGNORECASE)
        for match in matches:
            try:
                if len(match) == 3:
                    if patron.endswith('(\\d{4})'):
                        # Formato DD/MM/YYYY
                        dia, mes, año = int(match[0]), int(match[1]), int(match[2])
                        if año < 100:  # Convertir YY a YYYY
                            año += 2000 if año < 50 else 1900
                    elif 'de' in patron:
                        # Formato "15 de enero de 2024"
                        dia, mes_nombre, año = int(match[0]), match[1].lower(), int(match[2])
                        mes = meses.get(mes_nombre)
                        if not mes:
                            continue
                    else:
                        # Formato YYYY/MM/DD
                        año, mes, dia = int(match[0]), int(match[1]), int(match[2])
                    
                    # Validar fecha
                    if 1 <= mes <= 12 and 1 <= dia <= 31 and 2020 <= año <= 2030:
                        resultado['fecha'] = date(año, mes, dia)
                        break
            except (ValueError, TypeError):
                continue
        
        if resultado['fecha']:
            break
    
    return resultado

def extraer_datos_imagen(imagen_file):
    """
    Función principal para extraer datos de una imagen subida.
    
    Args:
        imagen_file: Archivo de imagen de Django
        
    Returns:
        dict: Diccionario con datos extraídos
    """
    try:
        # Guardar temporalmente la imagen
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as temp_file:
            for chunk in imagen_file.chunks():
                temp_file.write(chunk)
            temp_path = temp_file.name
        
        # Procesar la imagen
        resultado = procesar_imagen_comprobante(temp_path)
        
        # Limpiar archivo temporal
        os.unlink(temp_path)
        
        return resultado
        
    except Exception as e:
        print(f"Error extrayendo datos de imagen: {e}")
        return None

def procesar_historial_mercadopago(imagen_file):
    """
    Procesa una imagen del historial de MercadoPago para extraer múltiples gastos.
    
    Args:
        imagen_file: Archivo de imagen de Django con el historial
        
    Returns:
        list: Lista de diccionarios con gastos extraídos
    """
    try:
        if not imagen_file:
            return []
            
        # Verificar si Tesseract está disponible
        if not hasattr(pytesseract.pytesseract, 'tesseract_cmd') or not pytesseract.pytesseract.tesseract_cmd:
            print("Tesseract no está configurado correctamente")
            return []
            
        # Guardar temporalmente la imagen
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as temp_file:
            for chunk in imagen_file.chunks():
                temp_file.write(chunk)
            temp_path = temp_file.name
        
        # Procesar la imagen
        imagen = cv2.imread(temp_path)
        if imagen is None:
            os.unlink(temp_path)
            return []
            
        # Convertir a escala de grises
        gris = cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY)
        
        # Aplicar filtros para mejorar la legibilidad
        gris = cv2.medianBlur(gris, 3)
        gris = cv2.convertScaleAbs(gris, alpha=1.5, beta=30)
        binario = cv2.adaptiveThreshold(gris, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
        
        # Convertir a PIL Image para pytesseract
        pil_imagen = Image.fromarray(binario)
        
        # Extraer texto usando OCR
        try:
            # Intentar primero con español, luego con inglés si falla
            try:
                texto = pytesseract.image_to_string(pil_imagen, lang='spa')
            except Exception as e:
                # Si falla el español, usar inglés por defecto
                texto = pytesseract.image_to_string(pil_imagen, lang='eng')
        except pytesseract.TesseractNotFoundError:
            print("Tesseract no encontrado. Por favor instale Tesseract OCR.")
            os.unlink(temp_path)
            return []
        except Exception as ocr_error:
            print(f"Error en OCR: {ocr_error}")
            try:
                # Último intento sin especificar idioma
                texto = pytesseract.image_to_string(pil_imagen)
            except Exception as final_error:
                print(f"Error final en OCR: {final_error}")
                os.unlink(temp_path)
                return []
        
        # Limpiar archivo temporal
        os.unlink(temp_path)
        
        # Extraer múltiples gastos del texto
        gastos = extraer_gastos_historial(texto)
        
        return gastos
        
    except Exception as e:
        print(f"Error procesando historial: {e}")
        return []

def extraer_gastos_historial(texto):
    """
    Extrae múltiples gastos del texto del historial de MercadoPago.
    
    Args:
        texto: Texto extraído por OCR del historial
        
    Returns:
        list: Lista de diccionarios con gastos extraídos
    """
    gastos = []
    
    # Dividir el texto en líneas
    lineas = texto.split('\n')
    
    # Patrones para identificar transacciones de MercadoPago (solo gastos, sin signo +)
    # Excluir líneas que contengan '+' antes del monto (ingresos)
    patrones_transaccion = [
        # Patrones específicos para montos como 7.000, 5.000, 26.000, 12.000
        r'(.+?)\s*\$?\s*([0-9]{1,3}\.[0-9]{3})\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})?',
        r'(.+?)\s*([0-9]{1,3}\.[0-9]{3})\s*\$?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})?',
        # Patrones para montos con comas como separador de miles
        r'(.+?)\s*\$?\s*([0-9]{1,3},[0-9]{3})\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})?',
        r'(.+?)\s*([0-9]{1,3},[0-9]{3})\s*\$?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})?',
        # Patrones más flexibles para capturar cualquier línea con monto
        r'(.+?)\s*\$\s*([0-9]{1,3}(?:[.,][0-9]{3})*(?:[.,][0-9]{1,2})?)\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})?',
        r'(.+?)\s*([0-9]{1,3}(?:[.,][0-9]{3})*(?:[.,][0-9]{1,2})?)\s*\$\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})?',
        # Patrones específicos para tipos de transacción
        r'Pago\s+(.+?)\s*\$\s*([0-9]{1,3}(?:[.,][0-9]{3})*(?:[.,][0-9]{1,2})?)\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})?',
        r'Transferencia\s+(.+?)\s*\$\s*([0-9]{1,3}(?:[.,][0-9]{3})*(?:[.,][0-9]{1,2})?)\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})?',
        # Patrón para líneas que solo contienen monto (sin descripción clara)
        r'\$\s*([0-9]{1,3}(?:[.,][0-9]{3})*(?:[.,][0-9]{1,2})?)\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})?',
        r'([0-9]{1,3}(?:[.,][0-9]{3})*(?:[.,][0-9]{1,2})?)\s*\$\s*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})?',
    ]
    
    # Palabras clave para identificar gastos (no ingresos)
    palabras_gasto = ['pago', 'compra', 'transferencia', 'débito', 'gasto', 'factura', 'servicio']
    palabras_ingreso = ['recibido', 'ingreso', 'depósito', 'crédito', 'cobro']
    
    # Procesar cada línea
    for i, linea in enumerate(lineas):
        linea = linea.strip()
        print(f"Procesando línea {i}: '{linea}'")
        
        if not linea or len(linea) < 5:
            print(f"Línea {i} descartada: muy corta")
            continue
            
        # Filtrar líneas que contengan '+' antes del monto (ingresos)
        if re.search(r'\+\s*\$?\s*[0-9]', linea) or re.search(r'\+\s*[0-9]', linea):
            print(f"Línea {i} descartada: contiene signo '+'")
            continue
            
        # Buscar patrones de transacción
        patron_encontrado = False
        for j, patron in enumerate(patrones_transaccion):
            match = re.search(patron, linea, re.IGNORECASE)
            if match:
                print(f"Línea {i} coincide con patrón {j}: {patron}")
                grupos = match.groups()
                print(f"Grupos capturados: {grupos}")
                
                # Manejar diferentes números de grupos según el patrón
                if len(grupos) >= 2:
                    descripcion = grupos[0].strip() if grupos[0] else ''
                    monto_str = grupos[1] if grupos[1] else ''
                    fecha_str = grupos[2] if len(grupos) > 2 and grupos[2] else ''
                elif len(grupos) == 1:
                    # Solo monto, sin descripción
                    descripcion = ''
                    monto_str = grupos[0] if grupos[0] else ''
                    fecha_str = ''
                else:
                    continue
                    
                patron_encontrado = True
                
                # Filtrar solo gastos (no ingresos)
                # Verificar que no tenga signo '+' en la línea (principal filtro)
                tiene_signo_mas = '+' in linea
                
                # Excluir solo si tiene signo '+' (más permisivo)
                if tiene_signo_mas:
                    continue
                    
                # Verificar palabras clave de ingreso solo como filtro secundario
                es_ingreso_claro = any(palabra in linea.lower() for palabra in ['recibido', 'ingreso', 'depósito', 'crédito'])
                if es_ingreso_claro:
                    continue
                
                # Procesar monto
                monto = None
                if monto_str:
                    try:
                        print(f"Procesando monto_str: '{monto_str}'")
                        # Normalizar formato de número
                        if ',' in monto_str and '.' in monto_str:
                            if monto_str.rfind(',') > monto_str.rfind('.'):
                                # Formato: 1.234,56 -> 1234.56
                                monto_str = monto_str.replace('.', '').replace(',', '.')
                            else:
                                # Formato: 1,234.56 -> 1234.56
                                monto_str = monto_str.replace(',', '')
                        elif ',' in monto_str:
                            if len(monto_str.split(',')[-1]) == 2:
                                # Formato: 1234,56 -> 1234.56
                                monto_str = monto_str.replace(',', '.')
                            else:
                                # Formato: 1,234 -> 1234
                                monto_str = monto_str.replace(',', '')
                        elif '.' in monto_str:
                            # Verificar si es separador de miles o decimal
                            if len(monto_str.split('.')[-1]) == 3:
                                # Formato: 7.000 -> 7000 (separador de miles)
                                monto_str = monto_str.replace('.', '')
                            # Si tiene 1 o 2 dígitos después del punto, es decimal
                        
                        monto = float(monto_str)
                        print(f"Monto procesado: {monto}")
                    except (ValueError, InvalidOperation) as e:
                        print(f"Error procesando monto '{monto_str}': {e}")
                        continue
                
                # Procesar fecha
                fecha = None
                if fecha_str:
                    try:
                        # Intentar diferentes formatos de fecha
                        for formato in ['%d/%m/%Y', '%d-%m-%Y', '%d/%m/%y', '%d-%m-%y']:
                            try:
                                fecha = datetime.strptime(fecha_str, formato).date()
                                break
                            except ValueError:
                                continue
                    except:
                        pass
                
                # Si no hay fecha en la línea, buscar en líneas cercanas
                if not fecha:
                    for j in range(max(0, i-2), min(len(lineas), i+3)):
                        fecha_match = re.search(r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})', lineas[j])
                        if fecha_match:
                            try:
                                fecha_str = fecha_match.group(1)
                                for formato in ['%d/%m/%Y', '%d-%m-%Y', '%d/%m/%y', '%d-%m-%y']:
                                    try:
                                        fecha = datetime.strptime(fecha_str, formato).date()
                                        break
                                    except ValueError:
                                        continue
                                if fecha:
                                    break
                            except:
                                continue
                
                # Todos los gastos del historial se marcan como no prioritarios
                prioridad = 'baja'  # Se mapea a 'no_prioritario' en el modelo
                
                # Limpiar descripción
                if descripcion:
                    descripcion = re.sub(r'[^a-zA-ZáéíóúÁÉÍÓÚñÑ0-9\s]', '', descripcion)
                    descripcion = ' '.join(descripcion.split())  # Normalizar espacios
                
                # Agregar gasto si tiene monto válido (más permisivo)
                if monto and monto > 0:
                    gasto = {
                        'descripcion': descripcion or 'Gasto desde historial',
                        'monto': monto,
                        'fecha': fecha or date.today(),
                        'prioridad': prioridad
                    }
                    gastos.append(gasto)
                    print(f"Gasto agregado: {gasto}")
                    break  # Solo un patrón por línea
                else:
                    print(f"Gasto no agregado - monto inválido: {monto}")
                    
        if not patron_encontrado:
            print(f"Línea {i} no coincide con ningún patrón")
    
    # Filtrar gastos duplicados y validar
    gastos_validos = []
    for gasto in gastos:
        if gasto['monto'] and gasto['monto'] > 0:
            # Evitar duplicados basados en monto y descripción
            duplicado = False
            for gasto_existente in gastos_validos:
                if (abs(gasto['monto'] - gasto_existente['monto']) < 0.01 and 
                    gasto['descripcion'].lower() == gasto_existente['descripcion'].lower()):
                    duplicado = True
                    break
            
            if not duplicado:
                gastos_validos.append(gasto)
    
    return gastos_validos[:20]  # Limitar a 20 gastos máximo


def procesar_pdf_tarjeta_credito(pdf_file):
    """
    Procesa un PDF de tarjeta de crédito para extraer el total de gastos.
    
    Args:
        pdf_file: Archivo PDF de Django con el estado de cuenta
        
    Returns:
        dict: Diccionario con el total extraído y descripción
    """
    try:
        import pdfplumber
        import tempfile
        import os
        
        if not pdf_file:
            return None
            
        # Guardar temporalmente el PDF
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
            for chunk in pdf_file.chunks():
                temp_file.write(chunk)
            temp_path = temp_file.name
        
        # Extraer texto del PDF
        texto_completo = ""
        with pdfplumber.open(temp_path) as pdf:
            for page in pdf.pages:
                texto_pagina = page.extract_text()
                if texto_pagina:
                    texto_completo += texto_pagina + "\n"
        
        # Limpiar archivo temporal
        os.unlink(temp_path)
        
        if not texto_completo:
            return None
            
        # Extraer el total del estado de cuenta
        total_extraido = extraer_total_tarjeta_credito(texto_completo)
        
        if total_extraido:
            return {
                'descripcion': f"Estado de cuenta - {total_extraido.get('periodo', 'Mes actual')}",
                'monto': total_extraido['monto'],
                'detalles': total_extraido.get('detalles', '')
            }
        
        return None
        
    except Exception as e:
        print(f"Error procesando PDF: {e}")
        return None


def extraer_total_tarjeta_credito(texto):
    """
    Extrae el total a pagar del texto del estado de cuenta de tarjeta de crédito.
    
    Args:
        texto: Texto extraído del PDF
        
    Returns:
        dict: Diccionario con monto y detalles extraídos
    """
    try:
        # Normalizar texto
        texto = texto.upper()
        lineas = texto.split('\n')
        
        # Patrones para buscar el total a pagar
        patrones_total = [
            r'TOTAL\s+A\s+PAGAR[:\s]*\$?\s*([0-9]{1,3}(?:[.,][0-9]{3})*(?:[.,][0-9]{1,2})?)',
            r'SALDO\s+ACTUAL[:\s]*\$?\s*([0-9]{1,3}(?:[.,][0-9]{3})*(?:[.,][0-9]{1,2})?)',
            r'MONTO\s+TOTAL[:\s]*\$?\s*([0-9]{1,3}(?:[.,][0-9]{3})*(?:[.,][0-9]{1,2})?)',
            r'TOTAL\s+FACTURADO[:\s]*\$?\s*([0-9]{1,3}(?:[.,][0-9]{3})*(?:[.,][0-9]{1,2})?)',
            r'PAGO\s+MÍNIMO[:\s]*\$?\s*([0-9]{1,3}(?:[.,][0-9]{3})*(?:[.,][0-9]{1,2})?)',
            r'NUEVO\s+SALDO[:\s]*\$?\s*([0-9]{1,3}(?:[.,][0-9]{3})*(?:[.,][0-9]{1,2})?)',
            r'SALDO\s+PENDIENTE[:\s]*\$?\s*([0-9]{1,3}(?:[.,][0-9]{3})*(?:[.,][0-9]{1,2})?)',
        ]
        
        # Buscar periodo de facturación
        periodo = None
        patrones_periodo = [
            r'PERIODO[:\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\s*AL?\s*\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
            r'FACTURACIÓN[:\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\s*AL?\s*\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
            r'CORTE[:\s]*(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
        ]
        
        for patron in patrones_periodo:
            for linea in lineas:
                match = re.search(patron, linea)
                if match:
                    periodo = match.group(1)
                    break
            if periodo:
                break
        
        # Buscar el total
        for patron in patrones_total:
            for linea in lineas:
                match = re.search(patron, linea)
                if match:
                    monto_str = match.group(1)
                    
                    # Convertir a decimal
                    try:
                        # Normalizar formato de número
                        monto_str = monto_str.replace(',', '.')
                        # Si tiene más de un punto, el último es decimal
                        if monto_str.count('.') > 1:
                            partes = monto_str.split('.')
                            monto_str = ''.join(partes[:-1]) + '.' + partes[-1]
                        
                        monto = float(monto_str)
                        
                        if monto > 0:
                            return {
                                'monto': monto,
                                'periodo': periodo or 'Periodo no identificado',
                                'detalles': f'Extraído de: {linea.strip()}'
                            }
                    except (ValueError, InvalidOperation):
                        continue
        
        return None
        
    except Exception as e:
        print(f"Error extrayendo total: {e}")
        return None