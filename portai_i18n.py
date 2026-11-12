"""Centralized, offline localization for PortAI's terminal interface."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

LOCALES = ("pt-BR", "en", "es", "ar", "hi")
LOCALE_NAMES = {
    "pt-BR": "Português brasileiro",
    "en": "English",
    "es": "Español",
    "ar": "العربية",
    "hi": "हिन्दी",
}
CONFIG_PATH = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "offtec-portai" / "settings.json"

# Catalog keys are Portuguese source phrases used by the existing interface.
# Technical identifiers, commands, file paths and user-provided values are not keys.
_ROWS: dict[str, tuple[str, str, str, str]] = {
    "OFFTEC PORTAI": ("OFFTEC PORTAI", "OFFTEC PORTAI", "أوفتيك بورت آي", "ऑफटेक पोर्टएआई"),
    "Análise estática": ("Static analysis", "Análisis estático", "تحليل ساكن", "स्थिर विश्लेषण"),
    "cópias isoladas": ("isolated workspaces", "copias aisladas", "مساحات عمل معزولة", "अलग कार्यक्षेत्र"),
    "integração com Codex CLI": ("Codex CLI integration", "integración con Codex CLI", "تكامل Codex CLI", "Codex CLI एकीकरण"),
    "Encontrar e analisar projetos": ("Find and analyze projects", "Buscar y analizar proyectos", "العثور على المشاريع وتحليلها", "प्रोजेक्ट खोजें और विश्लेषण करें"),
    "Listar projetos detectados e escolher pelo número": ("List detected projects and choose by number", "Listar proyectos detectados y elegir por número", "عرض المشاريع المكتشفة والاختيار بالرقم", "पहचाने गए प्रोजेक्ट सूचीबद्ध करें और संख्या से चुनें"),
    "Caminho completo": ("Full path", "Ruta completa", "المسار الكامل", "पूरा पथ"),
    "01 — PROJETOS": ("01 — PROJECTS", "01 — PROYECTOS", "01 — المشاريع", "01 — प्रोजेक्ट"),
    "02 — APK BUILD CENTER": ("02 — APK BUILD CENTER", "02 — CENTRO DE COMPILACIÓN APK", "02 — مركز بناء APK", "02 — APK बिल्ड सेंटर"),
    "03 — TRADUÇÃO": ("03 — TRANSLATION", "03 — TRADUCCIÓN", "03 — الترجمة", "03 — अनुवाद"),
    "04 — GAME PORTABILITY": ("04 — GAME PORTABILITY", "04 — PORTABILIDAD DE JUEGOS", "04 — قابلية نقل الألعاب", "04 — गेम पोर्टेबिलिटी"),
    "05 — CONFIGURAÇÕES": ("05 — SETTINGS", "05 — CONFIGURACIÓN", "05 — الإعدادات", "05 — सेटिंग्स"),
    "Histórico e relatórios": ("History and reports", "Historial e informes", "السجل والتقارير", "इतिहास और रिपोर्ट"),
    "APK Build Center": ("APK Build Center", "Centro de compilación APK", "مركز بناء APK", "APK बिल्ड सेंटर"),
    "Reconstruir APK com Apktool": ("Rebuild APK with Apktool", "Reconstruir APK con Apktool", "إعادة بناء APK باستخدام Apktool", "Apktool से APK फिर बनाएँ"),
    "Assinar APK com sua keystore": ("Sign APK with your keystore", "Firmar APK con su keystore", "توقيع APK باستخدام keystore الخاصة بك", "अपनी keystore से APK साइन करें"),
    "Verificar integridade e assinatura": ("Check integrity and signature", "Verificar integridad y firma", "التحقق من السلامة والتوقيع", "इंटीग्रिटी और हस्ताक्षर जाँचें"),
    "Alinhar APK com zipalign": ("Align APK with zipalign", "Alinear APK con zipalign", "محاذاة APK باستخدام zipalign", "zipalign से APK अलाइन करें"),
    "Histórico de builds": ("Build history", "Historial de compilaciones", "سجل عمليات البناء", "बिल्ड इतिहास"),
    "Verificar qualidade das traduções": ("Check translation quality", "Verificar la calidad de las traducciones", "التحقق من جودة الترجمات", "अनुवाद की गुणवत्ता जाँचें"),
    "Analisar jogos": ("Analyze games", "Analizar juegos", "تحليل الألعاب", "गेम का विश्लेषण करें"),
    "Planejar adaptação": ("Plan adaptation", "Planificar adaptación", "تخطيط التكييف", "अनुकूलन की योजना बनाएँ"),
    "Reconstruir com Codex": ("Rebuild with Codex", "Reconstruir con Codex", "إعادة البناء باستخدام Codex", "Codex से पुनर्निर्माण करें"),
    "Ajuda e informações": ("Help and information", "Ayuda e información", "المساعدة والمعلومات", "सहायता और जानकारी"),
    "Verificar dependências": ("Check dependencies", "Verificar dependencias", "التحقق من التبعيات", "निर्भरताएँ जाँचें"),
    "05 — SISTEMA E CONFIGURAÇÕES": ("05 — SYSTEM AND SETTINGS", "05 — SISTEMA Y CONFIGURACIÓN", "05 — النظام والإعدادات", "05 — सिस्टम और सेटिंग्स"),
    "Instalar o que falta": ("Install what is missing", "Instalar lo que falta", "تثبيت ما ينقص", "जो कमी है उसे इंस्टॉल करें"),
    "Onde fica cada coisa": ("Where everything is", "Dónde está cada cosa", "أين يوجد كل شيء", "हर चीज़ कहाँ है"),
    "Atualizar o PortAI": ("Update PortAI", "Actualizar PortAI", "تحديث PortAI", "PortAI अपडेट करें"),
    "Salvar diagnóstico em JSON": ("Save diagnostics as JSON", "Guardar diagnóstico en JSON", "حفظ التشخيص بصيغة JSON", "निदान JSON में सहेजें"),
    "DIAGNÓSTICO DO AMBIENTE": ("ENVIRONMENT DIAGNOSTICS", "DIAGNÓSTICO DEL ENTORNO", "تشخيص البيئة", "पर्यावरण निदान"),
    "ONDE FICA CADA COISA": ("WHERE EVERYTHING IS", "DÓNDE ESTÁ CADA COSA", "أين يوجد كل شيء", "हर चीज़ कहाँ है"),
    "06 — IA LOCAL": ("06 — LOCAL AI", "06 — IA LOCAL", "06 — ذكاء اصطناعي محلي", "06 — लोकल एआई"),
    "Compilar projeto Android": ("Build Android project", "Compilar proyecto Android", "بناء مشروع Android", "Android प्रोजेक्ट बिल्ड करें"),
    "Pasta do projeto Android": ("Android project folder", "Carpeta del proyecto Android", "مجلد مشروع Android", "Android प्रोजेक्ट फ़ोल्डर"),
    "Projeto para compilar": ("Project to build", "Proyecto para compilar", "المشروع المراد بناؤه", "बिल्ड के लिए प्रोजेक्ट"),
    "Executar assembleDebug neste projeto?": ("Run assembleDebug for this project?", "¿Ejecutar assembleDebug en este proyecto?", "تنفيذ assembleDebug لهذا المشروع؟", "इस प्रोजेक्ट के लिए assembleDebug चलाएँ?"),
    "Caminho do APK de entrada": ("Path to input APK", "Ruta del APK de entrada", "مسار APK للإدخال", "इनपुट APK का पथ"),
    "Caminho do APK para verificar": ("Path to APK to verify", "Ruta del APK que se verificará", "مسار APK للتحقق منه", "जाँच के लिए APK पथ"),
    "Caminho da sua keystore": ("Path to your keystore", "Ruta de su keystore", "مسار keystore الخاصة بك", "आपकी keystore का पथ"),
    "Senha da keystore: ": ("Keystore password: ", "Contraseña de keystore: ", "كلمة مرور keystore: ", "Keystore पासवर्ड: "),
    "Senha da chave: ": ("Key password: ", "Contraseña de clave: ", "كلمة مرور المفتاح: ", "की पासवर्ड: "),
    "Assinar para um novo arquivo neste workspace?": ("Sign to a new file in this workspace?", "¿Firmar en un archivo nuevo en este espacio de trabajo?", "التوقيع إلى ملف جديد في مساحة العمل هذه؟", "इस workspace में नई फ़ाइल पर साइन करें?"),
    "APK válido e keystore existente são necessários.": ("A valid APK and existing keystore are required.", "Se requiere un APK válido y una keystore existente.", "يلزم APK صالح وkeystore موجودة.", "वैध APK और मौजूदा keystore आवश्यक हैं।"),
    "Ainda não há builds registrados.": ("No builds have been recorded yet.", "Aún no hay compilaciones registradas.", "لم يتم تسجيل أي عمليات بناء بعد.", "अभी तक कोई बिल्ड दर्ज नहीं है।"),
    "Voltar": ("Back", "Volver", "رجوع", "वापस"),
    "Voltar ao menu": ("Return to menu", "Volver al menú", "العودة إلى القائمة", "मेनू पर लौटें"),
    "Portar com Codex": ("Port with Codex", "Portar con Codex", "النقل باستخدام Codex", "Codex से पोर्ट करें"),
    "Abrir o ambiente persistente de reconstrução Android": ("Open the persistent Android reconstruction workspace", "Abrir el entorno persistente de reconstrucción de Android", "فتح مساحة إعادة بناء Android المستمرة", "स्थायी Android पुनर्निर्माण कार्यस्थान खोलें"),
    "Diagnóstico": ("Diagnostics", "Diagnóstico", "التشخيص", "निदान"),
    "Verificar Python, Codex, Git e SDK Android": ("Check Python, Codex, Git, and Android SDK", "Comprobar Python, Codex, Git y Android SDK", "التحقق من Python وCodex وGit وAndroid SDK", "Python, Codex, Git और Android SDK जाँचें"),
    "Reconstrução Android com Codex": ("Android reconstruction with Codex", "Reconstrucción de Android con Codex", "إعادة بناء Android باستخدام Codex", "Codex के साथ Android पुनर्निर्माण"),
    "Ambiente persistente para análise, adaptação e APK": ("Persistent workspace for analysis, adaptation, and APK", "Entorno persistente para análisis, adaptación y APK", "مساحة عمل مستمرة للتحليل والتعديل وAPK", "विश्लेषण, अनुकूलन और APK के लिए स्थायी कार्यस्थान"),
    "Universal Translation Engine • revisão e localização": ("Universal Translation Engine • review and localization", "Universal Translation Engine • revisión y localización", "محرك الترجمة الشامل • المراجعة والتعريب", "यूनिवर्सल ट्रांसलेशन इंजन • समीक्षा और स्थानीयकरण"),
    "Extrair, localizar, reconstruir e assinar com sua keystore": ("Extract, localize, rebuild, and sign with your keystore", "Extraer, localizar, reconstruir y firmar con su keystore", "استخراج المحتوى وتعريبه وإعادة بنائه وتوقيعه باستخدام keystore الخاصة بك", "अपनी keystore से निकालें, स्थानीयकरण करें, पुनर्निर्माण और हस्ताक्षर करें"),
    "Analisar portabilidade, autorizar arquivos e trabalhar com Codex": ("Analyze portability, authorize files, and work with Codex", "Analizar portabilidad, autorizar archivos y trabajar con Codex", "تحليل قابلية النقل وتفويض الملفات والعمل مع Codex", "पोर्टेबिलिटी विश्लेषण, फ़ाइल अनुमति और Codex के साथ काम"),
    "Autenticação": ("Authentication", "Autenticación", "المصادقة", "प्रमाणीकरण"),
    "Abrir pasta de relatórios": ("Open reports folder", "Abrir carpeta de informes", "فتح مجلد التقارير", "रिपोर्ट फ़ोल्डर खोलें"),
    "Listar relatórios gerados": ("List generated reports", "Listar informes generados", "عرض التقارير المنشأة", "बनी हुई रिपोर्ट सूचीबद्ध करें"),
    "Continuar conversa no workspace": ("Continue conversation in workspace", "Continuar conversación en el espacio de trabajo", "متابعة المحادثة في مساحة العمل", "कार्यस्थान में बातचीत जारी रखें"),
    "Inspecionar projeto": ("Inspect project", "Inspeccionar proyecto", "فحص المشروع", "प्रोजेक्ट का निरीक्षण करें"),
    "Solicitar alterações": ("Request changes", "Solicitar cambios", "طلب التغييرات", "बदलाव का अनुरोध करें"),
    "Executar build": ("Run build", "Ejecutar build", "تنفيذ البناء", "बिल्ड चलाएँ"),
    "Mostrar progresso": ("Show progress", "Mostrar progreso", "عرض التقدم", "प्रगति दिखाएँ"),
    "Voltar ao menu": ("Return to menu", "Volver al menú", "العودة إلى القائمة", "मेनू पर लौटें"),
    "Iniciar análise": ("Start analysis", "Iniciar análisis", "بدء التحليل", "विश्लेषण शुरू करें"),
    "Executar Codex": ("Run Codex", "Ejecutar Codex", "تشغيل Codex", "Codex चलाएँ"),
    "Continuar sessão": ("Resume session", "Continuar sesión", "متابعة الجلسة", "सत्र जारी रखें"),
    "Autorizar e executar alterações": ("Authorize and apply changes", "Autorizar y realizar cambios", "تفويض التغييرات وتنفيذها", "बदलाव अधिकृत करें और लागू करें"),
    "Gerar relatório": ("Generate report", "Generar informe", "إنشاء تقرير", "रिपोर्ट बनाएँ"),
    "Confirmação necessária": ("Confirmation required", "Se requiere confirmación", "يلزم التأكيد", "पुष्टि आवश्यक है"),
    "Operação concluída": ("Operation complete", "Operación completada", "اكتملت العملية", "कार्य पूरा हुआ"),
    "Abrir pasta de relatórios": ("Open reports folder", "Abrir carpeta de informes", "فتح مجلد التقارير", "रिपोर्ट फ़ोल्डर खोलें"),
    "Verificar ferramentas de build": ("Check build tools", "Comprobar herramientas de compilación", "التحقق من أدوات البناء", "बिल्ड टूल जाँचें"),
    "Reconstrução": ("Workspace", "Espacio de trabajo", "مساحة العمل", "कार्यस्थान"),
    "Universal Translation Engine": ("Universal Translation Engine", "Universal Translation Engine", "Universal Translation Engine", "Universal Translation Engine"),
    "revisão e localização": ("review and localization", "revisión y localización", "المراجعة والتعريب", "समीक्षा और स्थानीयकरण"),
    "Traduzir projeto": ("Translate project", "Traducir proyecto", "ترجمة المشروع", "प्रोजेक्ट का अनुवाद करें"),
    "Traduzir APK Android": ("Translate Android APK", "Traducir APK de Android", "ترجمة APK أندرويد", "Android APK का अनुवाद"),
    "AI Game Recreation Engine": ("AI Game Recreation Engine", "AI Game Recreation Engine", "AI Game Recreation Engine", "AI Game Recreation Engine"),
    "Analisar portabilidade, autorizar arquivos e trabalhar com Codex": ("Analyze portability, authorize files, and work with Codex", "Analizar portabilidad, autorizar archivos y trabajar con Codex", "تحليل قابلية النقل وتفويض الملفات والعمل مع Codex", "पोर्टेबिलिटी विश्लेषण, फ़ाइल अनुमति और Codex के साथ काम"),
    "Sair": ("Exit", "Salir", "خروج", "बाहर निकलें"),
    "Encerrar com segurança": ("Exit safely", "Salir de forma segura", "إنهاء بأمان", "सुरक्षित रूप से बंद करें"),
    "Opção": ("Option", "Opción", "الخيار", "विकल्प"),
    "Ferramenta": ("Tool", "Herramienta", "الأداة", "टूल"),
    "Descrição": ("Description", "Descripción", "الوصف", "विवरण"),
    "PortAI": ("PortAI", "PortAI", "PortAI", "PortAI"),
    "PROGRESSO": ("PROGRESS", "PROGRESO", "التقدم", "प्रगति"),
    "Estado": ("Status", "Estado", "الحالة", "स्थिति"),
    "Origem": ("Source", "Origen", "المصدر", "स्रोत"),
    "Workspace": ("Workspace", "Espacio de trabajo", "مساحة العمل", "कार्यस्थान"),
    "Sessão Codex": ("Codex session", "Sesión de Codex", "جلسة Codex", "Codex सत्र"),
    "Último erro": ("Last error", "Último error", "آخر خطأ", "अंतिम त्रुटि"),
    "indisponível": ("unavailable", "no disponible", "غير متاح", "उपलब्ध नहीं"),
    "nenhum": ("none", "ninguno", "لا شيء", "कोई नहीं"),
    "não encontrado": ("not found", "no encontrado", "غير موجود", "नहीं मिला"),
    "Pasta inválida.": ("Invalid folder.", "Carpeta no válida.", "مجلد غير صالح.", "अमान्य फ़ोल्डर।"),
    "Arquivo APK não encontrado.": ("APK file not found.", "No se encontró el archivo APK.", "لم يتم العثور على ملف APK.", "APK फ़ाइल नहीं मिली।"),
    "Keystore não encontrada.": ("Keystore not found.", "No se encontró el keystore.", "لم يتم العثور على keystore.", "कीस्टोर नहीं मिली।"),
    "Dependências obrigatórias ausentes": ("Required dependencies missing", "Faltan dependencias obligatorias", "التبعيات المطلوبة غير متوفرة", "आवश्यक निर्भरताएँ मौजूद नहीं हैं"),
    "Falha ao iniciar": ("Could not start", "No se pudo iniciar", "تعذر البدء", "शुरू नहीं हो सका"),
    "Falha na análise": ("Analysis failed", "Error en el análisis", "فشل التحليل", "विश्लेषण विफल"),
    "Falha ao executar Codex": ("Codex execution failed", "Falló la ejecución de Codex", "فشل تشغيل Codex", "Codex चलाने में विफल"),
    "Execução interrompida": ("Execution interrupted", "Ejecución interrumpida", "تم إيقاف التنفيذ", "निष्पादन रोक दिया गया"),
    "Autenticação": ("Authentication", "Autenticación", "المصادقة", "प्रमाणीकरण"),
    "execute": ("run", "ejecute", "شغّل", "चलाएँ"),
    "para conferir": ("to check", "para comprobar", "للتحقق", "जाँचने के लिए"),
    "A disponibilidade de ferramentas não garante que um projeto possa ser portado.": ("Available tools do not guarantee that a project can be ported.", "La disponibilidad de herramientas no garantiza que un proyecto pueda portarse.", "توفر الأدوات لا يضمن إمكانية نقل المشروع.", "टूल उपलब्ध होने से प्रोजेक्ट पोर्ट होना सुनिश्चित नहीं होता।"),
    "Procurando aplicativos desktop nas raízes configuradas...": ("Searching configured roots for desktop apps...", "Buscando aplicaciones de escritorio en las ubicaciones configuradas...", "جارٍ البحث عن تطبيقات سطح المكتب في المسارات المحددة...", "कॉन्फ़िगर किए गए पथों में डेस्कटॉप ऐप खोज रहे हैं..."),
    "Nenhum projeto desktop com evidências suficientes foi encontrado.": ("No desktop project with sufficient evidence was found.", "No se encontró un proyecto de escritorio con evidencia suficiente.", "لم يتم العثور على مشروع سطح مكتب بأدلة كافية.", "पर्याप्त प्रमाण वाला डेस्कटॉप प्रोजेक्ट नहीं मिला।"),
    "Informe outra pasta de busca (Enter para voltar)": ("Enter another search folder (Enter to return)", "Indique otra carpeta de búsqueda (Enter para volver)", "أدخل مجلد بحث آخر (Enter للعودة)", "खोज के लिए दूसरा फ़ोल्डर दें (वापस जाने के लिए Enter)"),
    "Pressione Enter para voltar": ("Press Enter to return", "Pulse Enter para volver", "اضغط Enter للعودة", "वापस जाने के लिए Enter दबाएँ"),
    "Diretório adicional": ("Additional directory", "Directorio adicional", "مجلد إضافي", "अतिरिक्त डायरेक्टरी"),
    "Projeto": ("Project", "Proyecto", "المشروع", "प्रोजेक्ट"),
    "Raiz identificada": ("Detected root", "Raíz detectada", "المجلد الجذر المكتشف", "पहचाना गया रूट"),
    "Plataforma": ("Platform", "Plataforma", "النظام", "प्लेटफ़ॉर्म"),
    "Tipo": ("Type", "Tipo", "النوع", "प्रकार"),
    "Tecnologia": ("Technology", "Tecnología", "التقنية", "तकनीक"),
    "Evidência": ("Evidence", "Evidencia", "الدليل", "प्रमाण"),
    "Precisa de análise": ("Needs analysis", "Requiere análisis", "يتطلب التحليل", "विश्लेषण आवश्यक"),
    "Um .EXE sozinho não vira APK: normalmente precisamos do código-fonte e das dependências.": ("An .EXE alone cannot become an APK: source code and dependencies are usually required.", "Un .EXE por sí solo no se convierte en APK: normalmente se necesitan el código fuente y las dependencias.", "لا يمكن تحويل ملف .EXE وحده إلى APK؛ فعادةً ما يلزم توفر الشيفرة المصدرية والتبعيات.", ".EXE अकेले APK नहीं बनता: आमतौर पर सोर्स कोड और निर्भरताएँ चाहिए।"),
    "Opções numeradas correspondem às linhas da lista.": ("Numbers correspond to list entries.", "Los números corresponden a las filas de la lista.", "الأرقام تقابل عناصر القائمة.", "संख्याएँ सूची की प्रविष्टियों से मेल खाती हैं।"),
    "Digite 'a' para buscar em outro diretório; isso não amplia a busca automática.": ("Enter 'a' to search another directory; this does not expand automatic search.", "Escriba 'a' para buscar en otro directorio; esto no amplía la búsqueda automática.", "أدخل 'a' للبحث في مجلد آخر؛ لن يؤدي ذلك إلى توسيع البحث التلقائي.", "दूसरी डायरेक्टरी खोजने के लिए 'a' लिखें; इससे स्वचालित खोज का दायरा नहीं बढ़ेगा।"),
    "Escolha um projeto fora da pasta do PortAI.": ("Choose a project outside the PortAI folder.", "Elija un proyecto fuera de la carpeta de PortAI.", "اختر مشروعًا خارج مجلد PortAI.", "PortAI फ़ोल्डर से बाहर का प्रोजेक्ट चुनें।"),
    "Estado da workspace": ("Workspace state", "Estado del espacio de trabajo", "حالة مساحة العمل", "कार्यस्थान स्थिति"),
    "não será associada automaticamente a outro projeto": ("will not be automatically associated with another project", "no se asociará automáticamente a otro proyecto", "لن يتم ربطها تلقائيًا بمشروع آخر", "इसे किसी अन्य प्रोजेक्ट से अपने आप नहीं जोड़ा जाएगा"),
    "Analisando a cópia existente": ("Analyzing existing copy", "Analizando la copia existente", "تحليل النسخة الحالية", "मौजूदा कॉपी का विश्लेषण"),
    "Criar uma cópia de trabalho isolada em workspaces/?": ("Create an isolated working copy in workspaces/?", "¿Crear una copia de trabajo aislada en workspaces/?", "إنشاء نسخة عمل معزولة في workspaces/?", "workspaces/ में अलग कार्यशील कॉपी बनाएँ?"),
    "Criar uma cópia isolada em workspaces/ para a sessão Codex?": ("Create an isolated copy in workspaces/ for the Codex session?", "¿Crear una copia aislada en workspaces/ para la sesión de Codex?", "إنشاء نسخة معزولة في workspaces/ لجلسة Codex؟", "Codex सत्र के लिए workspaces/ में अलग कॉपी बनाएँ?"),
    "Codex CLI não está no PATH.": ("Codex CLI is not in PATH.", "Codex CLI no está en PATH.", "Codex CLI غير موجود في PATH.", "Codex CLI PATH में नहीं है।"),
    "não está no PATH.": ("is not in PATH.", "no está en PATH.", "غير موجود في PATH.", "PATH में नहीं है।"),
    "não encontrado no PATH.": ("not found in PATH.", "no se encontró en PATH.", "غير موجود في PATH.", "PATH में नहीं मिला।"),
    "Nenhum ID salvo para retomar": ("No saved ID to resume", "No hay un ID guardado para reanudar", "لا يوجد معرّف محفوظ للاستئناف", "फिर शुरू करने के लिए कोई ID सहेजी नहीं गई"),
    "Continuar conversa": ("Continue conversation", "Continuar conversación", "متابعة المحادثة", "बातचीत जारी रखें"),
    "Iniciando Codex interativo no workspace; saia do Codex para retornar aqui.": ("Starting interactive Codex in the workspace; exit Codex to return here.", "Iniciando Codex interactivo en el espacio de trabajo; salga de Codex para volver.", "بدء Codex التفاعلي في مساحة العمل؛ اخرج من Codex للعودة.", "कार्यस्थान में इंटरैक्टिव Codex शुरू हो रहा है; लौटने के लिए Codex से बाहर निकलें।"),
    "Aprovar esta tradução?": ("Approve this translation?", "¿Aprobar esta traducción?", "هل توافق على هذه الترجمة؟", "इस अनुवाद को स्वीकृत करें?"),
    "Pasta do projeto para traduzir": ("Project folder to translate", "Carpeta del proyecto que se traducirá", "مجلد المشروع المراد ترجمته", "अनुवाद के लिए प्रोजेक्ट फ़ोल्डर"),
    "Pasta do projeto": ("Project folder", "Carpeta del proyecto", "مجلد المشروع", "प्रोजेक्ट फ़ोल्डर"),
    "Pasta inválida": ("Invalid folder", "Carpeta no válida", "مجلد غير صالح", "अमान्य फ़ोल्डर"),
    "Idioma original": ("Source language", "Idioma de origen", "اللغة المصدر", "स्रोत भाषा"),
    "Idiomas de destino separados por vírgula": ("Target languages, comma-separated", "Idiomas de destino separados por comas", "اللغات المستهدفة مفصولة بفواصل", "लक्ष्य भाषाएँ, अल्पविराम से अलग करें"),
    "Seleção de idiomas inválida": ("Invalid language selection", "Selección de idiomas no válida", "اختيار اللغة غير صالح", "अमान्य भाषा चयन"),
    "Pasta de saída (originais permanecem intactos)": ("Output folder (originals remain unchanged)", "Carpeta de salida (los originales permanecen intactos)", "مجلد الإخراج (تبقى الملفات الأصلية دون تغيير)", "आउटपुट फ़ोल्डर (मूल फ़ाइलें अपरिवर्तित रहेंगी)"),
    "strings para revisão": ("strings for review", "cadenas para revisar", "نصوص للمراجعة", "समीक्षा के लिए स्ट्रिंग"),
    "propostas para revisão. Nenhuma será aplicada sem aprovação.": ("proposals for review. None will be applied without approval.", "propuestas para revisar. Ninguna se aplicará sin aprobación.", "مقترحات للمراجعة. لن يتم تطبيق أي منها دون موافقة.", "समीक्षा के लिए प्रस्ताव। स्वीकृति के बिना कोई लागू नहीं होगा।"),
    "O provedor não produziu traduções.": ("The provider returned no translations.", "El proveedor no generó traducciones.", "لم يُرجع المزود أي ترجمات.", "प्रदाता ने कोई अनुवाद नहीं दिया।"),
    "configure um provedor e tente novamente.": ("configure a provider and try again.", "configure un proveedor e inténtelo de nuevo.", "قم بإعداد مزود وحاول مرة أخرى.", "प्रदाता कॉन्फ़िगर करके फिर प्रयास करें।"),
    "Falha no Universal Translation Engine": ("Universal Translation Engine failed", "Error en Universal Translation Engine", "فشل محرك الترجمة الشامل", "यूनिवर्सल ट्रांसलेशन इंजन विफल"),
    "Relatório:": ("Report:", "Informe:", "التقرير:", "रिपोर्ट:"),
    "Caminho do APK original": ("Path to original APK", "Ruta del APK original", "مسار APK الأصلي", "मूल APK का पथ"),
    "Idioma de destino": ("Target language", "Idioma de destino", "اللغة المستهدفة", "लक्ष्य भाषा"),
    "Caminho da sua keystore de assinatura": ("Path to your signing keystore", "Ruta de su keystore de firma", "مسار keystore التوقيع الخاصة بك", "अपनी साइनिंग कीस्टोर का पथ"),
    "Alias da chave": ("Key alias", "Alias de la clave", "اسم مفتاح التوقيع", "की अलियास"),
    "Idioma original das strings": ("Source language of strings", "Idioma de origen de las cadenas", "لغة النصوص المصدر", "स्ट्रिंग की स्रोत भाषा"),
    "Pacote": ("Package", "Paquete", "الحزمة", "पैकेज"),
    "Versão": ("Version", "Versión", "الإصدار", "संस्करण"),
    "Arquiteturas": ("Architectures", "Arquitecturas", "المعمارية", "आर्किटेक्चर"),
    "indisponível": ("unavailable", "no disponible", "غير متاح", "उपलब्ध नहीं"),
    "Aviso:": ("Warning:", "Aviso:", "تحذير:", "चेतावनी:"),
    "APK assinado e validado": ("APK signed and validated", "APK firmado y validado", "تم توقيع APK والتحقق منه", "APK हस्ताक्षरित और सत्यापित"),
    "Processamento não concluído": ("Processing incomplete", "Procesamiento incompleto", "لم تكتمل المعالجة", "प्रक्रिया पूरी नहीं हुई"),
    "Falha ao iniciar o tradutor de APK": ("Could not start APK translator", "No se pudo iniciar el traductor de APK", "تعذر بدء مترجم APK", "APK अनुवादक शुरू नहीं हो सका"),
    "Pasta raiz do projeto de jogo": ("Game project root folder", "Carpeta raíz del proyecto de juego", "المجلد الجذر لمشروع اللعبة", "गेम प्रोजेक्ट की रूट डायरेक्टरी"),
    "Escolha um projeto fora da pasta da PortAI.": ("Choose a project outside the PortAI folder.", "Elija un proyecto fuera de la carpeta de PortAI.", "اختر مشروعًا خارج مجلد PortAI.", "PortAI फ़ोल्डर से बाहर का प्रोजेक्ट चुनें।"),
    "ANÁLISE DE PORTABILIDADE DE JOGO": ("GAME PORTABILITY ANALYSIS", "ANÁLISIS DE PORTABILIDAD DEL JUEGO", "تحليل قابلية نقل اللعبة", "गेम पोर्टेबिलिटी विश्लेषण"),
    "Engine": ("Engine", "Motor", "المحرك", "इंजन"),
    "Arquivos": ("Files", "Archivos", "الملفات", "फ़ाइलें"),
    "scripts/código": ("scripts/code", "scripts/código", "البرامج/الشيفرة", "स्क्रिप्ट/कोड"),
    "Dependências identificadas": ("Dependencies identified", "Dependencias identificadas", "التبعيات المكتشفة", "पहचानी गई निर्भरताएँ"),
    "Incompatibilidades": ("Incompatibilities", "Incompatibilidades", "أوجه عدم التوافق", "असंगतियाँ"),
    "Build Android já configurado": ("Android build already configured", "Build de Android ya configurada", "تم إعداد بناء Android مسبقًا", "Android बिल्ड पहले से कॉन्फ़िगर है"),
    "sim, verificar antes de compilar": ("yes, verify before building", "sí, verificar antes de compilar", "نعم، تحقّق قبل البناء", "हाँ, बिल्ड से पहले जाँचें"),
    "não detectado": ("not detected", "no detectada", "غير مكتشف", "पता नहीं चला"),
    "Host indicado": ("Suggested host", "Host indicado", "النظام المضيف المقترح", "सुझाया गया होस्ट"),
    "Relatórios:": ("Reports:", "Informes:", "التقارير:", "रिपोर्ट:"),
    "Atualizar análise e plano": ("Refresh analysis and plan", "Actualizar análisis y plan", "تحديث التحليل والخطة", "विश्लेषण और योजना ताज़ा करें"),
    "Pedir revisão de plano ao Codex (somente leitura)": ("Ask Codex to review the plan (read-only)", "Pedir a Codex que revise el plan (solo lectura)", "طلب مراجعة الخطة من Codex (للقراءة فقط)", "Codex से योजना की समीक्षा माँगें (केवल पढ़ने योग्य)"),
    "Autorizar arquivos e solicitar adaptação ao Codex": ("Authorize files and request Codex adaptation", "Autorizar archivos y solicitar adaptación a Codex", "تفويض الملفات وطلب التعديل من Codex", "फ़ाइलें अधिकृत करें और Codex से अनुकूलन माँगें"),
    "Continuar sessão Codex persistente": ("Resume persistent Codex session", "Continuar sesión persistente de Codex", "متابعة جلسة Codex المستمرة", "स्थायी Codex सत्र जारी रखें"),
    "Mostrar progresso e arquivos alterados": ("Show progress and changed files", "Mostrar progreso y archivos modificados", "عرض التقدم والملفات المعدلة", "प्रगति और बदली हुई फ़ाइलें दिखाएँ"),
    "Recuperar backup dos arquivos autorizados": ("Restore authorized-file backup", "Restaurar copia de seguridad de archivos autorizados", "استعادة نسخة احتياطية للملفات المفوضة", "अधिकृत फ़ाइलों का बैकअप पुनर्स्थापित करें"),
    "Compilar build Gradle Android real": ("Run a real Android Gradle build", "Ejecutar una compilación Gradle real de Android", "تنفيذ بناء Gradle حقيقي لأندرويد", "वास्तविक Android Gradle बिल्ड चलाएँ"),
    "Voltar ao menu principal": ("Return to main menu", "Volver al menú principal", "العودة إلى القائمة الرئيسية", "मुख्य मेनू पर लौटें"),
    "Análise atualizada": ("Analysis updated", "Análisis actualizado", "تم تحديث التحليل", "विश्लेषण अपडेट हुआ"),
    "A análise não encontrou arquivos candidatos para autorização.": ("The analysis found no candidate files to authorize.", "El análisis no encontró archivos candidatos para autorizar.", "لم يعثر التحليل على ملفات مرشحة للتفويض.", "विश्लेषण में अनुमति के लिए कोई फ़ाइल नहीं मिली।"),
    "Índices exatos autorizados, separados por vírgula (0 cancela)": ("Exact authorized indices, comma-separated (0 cancels)", "Índices exactos autorizados, separados por comas (0 cancela)", "أرقام الملفات المفوضة مفصولة بفواصل (0 للإلغاء)", "अनुमत इंडेक्स अल्पविराम से अलग करें (0 रद्द करता है)"),
    "Use apenas índices numéricos.": ("Use numeric indices only.", "Use solo índices numéricos.", "استخدم أرقامًا فقط.", "केवल संख्यात्मक इंडेक्स दर्ज करें।"),
    "Um dos índices não corresponde à lista.": ("One of the indices is not in the list.", "Uno de los índices no corresponde a la lista.", "أحد الأرقام غير موجود في القائمة.", "दिए गए इंडेक्स में से एक सूची में नहीं है।"),
    "Arquivos modificados detectados": ("Changed files detected", "Archivos modificados detectados", "الملفات المعدلة المكتشفة", "बदली गई फ़ाइलें मिलीं"),
    "Nenhum ID de sessão persistente foi salvo ainda.": ("No persistent session ID has been saved yet.", "Aún no se ha guardado ningún ID de sesión persistente.", "لم يتم حفظ معرّف جلسة دائمة بعد.", "अभी तक कोई स्थायी सत्र ID सहेजी नहीं गई।"),
    "Estado da workspace não encontrado": ("Workspace state not found", "No se encontró el estado del espacio de trabajo", "لم يتم العثور على حالة مساحة العمل", "कार्यस्थान स्थिति नहीं मिली"),
    "não será associada automaticamente a outro projeto": ("will not be automatically associated with another project", "no se asociará automáticamente a otro proyecto", "لن يتم ربطها تلقائيًا بمشروع آخر", "इसे किसी अन्य प्रोजेक्ट से अपने आप नहीं जोड़ा जाएगा"),
    "Estado persistente da workspace inválido": ("Invalid persistent workspace state", "El estado persistente del espacio de trabajo no es válido", "حالة مساحة العمل الدائمة غير صالحة", "कार्यस्थान की स्थायी स्थिति अमान्य है"),
    "Codex CLI não encontrado no PATH.": ("Codex CLI not found in PATH.", "No se encontró Codex CLI en PATH.", "لم يتم العثور على Codex CLI في PATH.", "PATH में Codex CLI नहीं मिला।"),
    "Keystore não encontrada. O PortAI não extrai nem cria chaves de terceiros.": ("Keystore not found. PortAI does not extract or create third-party keys.", "No se encontró el keystore. PortAI no extrae ni crea claves de terceros.", "لم يتم العثور على keystore. لا يستخرج PortAI مفاتيح الجهات الأخرى ولا ينشئها.", "कीस्टोर नहीं मिली। PortAI तीसरे पक्ष की कुंजियाँ निकालता या बनाता नहीं है।"),
    "Execução interrompida; workspace e estado foram preservados.": ("Execution interrupted; workspace and state were preserved.", "Ejecución interrumpida; se conservaron el espacio de trabajo y el estado.", "تم إيقاف التنفيذ مع الحفاظ على مساحة العمل والحالة.", "निष्पादन रोक दिया गया; कार्यस्थान और स्थिति सुरक्षित रखी गई।"),
    "Nenhuma configuração de projeto foi encontrada nesse diretório.": ("No project configuration was found in this directory.", "No se encontró una configuración de proyecto en este directorio.", "لم يتم العثور على إعداد مشروع في هذا المجلد.", "इस डायरेक्टरी में प्रोजेक्ट कॉन्फ़िगरेशन नहीं मिला।"),
    "Nenhum APK não vazio encontrado.": ("No non-empty APK was found.", "No se encontró ningún APK no vacío.", "لم يتم العثور على APK غير فارغ.", "कोई गैर-खाली APK नहीं मिला।"),
    "A análise não encontrou arquivos candidatos para autorização.": ("The analysis found no candidate files to authorize.", "El análisis no encontró archivos candidatos para autorizar.", "لم يعثر التحليل على ملفات مرشحة للتفويض.", "विश्लेषण में अनुमति के लिए कोई फ़ाइल नहीं मिली।"),
    "Um dos índices não corresponde à lista.": ("One of the indices is not in the list.", "Uno de los índices no corresponde a la lista.", "أحد الأرقام غير موجود في القائمة.", "दिए गए इंडेक्स में से एक सूची में नहीं है।"),
    "Use apenas índices numéricos.": ("Use numeric indices only.", "Use solo índices numéricos.", "استخدم أرقامًا فقط.", "केवल संख्यात्मक इंडेक्स दर्ज करें।"),
    "Nenhuma string traduzível foi encontrada nos formatos suportados.": ("No translatable strings were found in supported formats.", "No se encontraron cadenas traducibles en los formatos compatibles.", "لم يتم العثور على نصوص قابلة للترجمة في التنسيقات المدعومة.", "समर्थित प्रारूपों में अनुवाद योग्य स्ट्रिंग नहीं मिलीं।"),
    "As strings ficam registradas como não traduzidas": ("Strings remain recorded as untranslated", "Las cadenas quedan registradas como no traducidas", "ستظل النصوص مسجلة على أنها غير مترجمة", "स्ट्रिंग का रिकॉर्ड अनुवादित नहीं के रूप में रहेगा"),
    "Codex CLI não está no PATH.": ("Codex CLI is not in PATH.", "Codex CLI no está en PATH.", "Codex CLI غير موجود في PATH.", "Codex CLI PATH में नहीं है।"),
    "Não há ID salvo para retomar": ("No saved ID to resume", "No hay un ID guardado para reanudar", "لا يوجد معرّف محفوظ للاستئناف", "फिर शुरू करने के लिए कोई ID सहेजी नहीं गई"),
    "Saída preservada": ("Output preserved", "Salida conservada", "تم الحفاظ على المخرجات", "आउटपुट सुरक्षित है"),
    "A execução excedeu o limite. Estado preservado": ("Execution timed out. State preserved", "La ejecución superó el límite. Estado conservado", "انتهت مهلة التنفيذ. تم الحفاظ على الحالة", "निष्पादन समय सीमा पार हुई। स्थिति सुरक्षित है"),
    "Falha ao recuperar backup": ("Backup restoration failed", "Falló la restauración de la copia de seguridad", "فشلت استعادة النسخة الاحتياطية", "बैकअप पुनर्स्थापित नहीं हो सका"),
    "O APK original não foi modificado": ("The original APK was not modified", "El APK original no se modificó", "لم يتم تعديل APK الأصلي", "मूल APK में बदलाव नहीं हुआ"),
    "Nenhum backup de arquivos autorizados foi encontrado.": ("No authorized-file backup was found.", "No se encontró una copia de seguridad de los archivos autorizados.", "لم يتم العثور على نسخة احتياطية للملفات المفوضة.", "अधिकृत फ़ाइलों का बैकअप नहीं मिला।"),
    "Recuperar arquivos conforme": ("Restore files from", "Restaurar archivos según", "استعادة الملفات من", "इससे फ़ाइलें पुनर्स्थापित करें"),
    "Falha ao recuperar backup": ("Backup restoration failed", "Falló la restauración de la copia de seguridad", "فشلت استعادة النسخة الاحتياطية", "बैकअप पुनर्स्थापित नहीं हो सका"),
    "Build não iniciado": ("Build not started", "Build no iniciada", "لم يبدأ البناء", "बिल्ड शुरू नहीं हुई"),
    "não encontrei configuração de aplicativo Gradle Android": ("no Android Gradle application configuration was found", "no se encontró configuración de aplicación Gradle de Android", "لم يتم العثور على إعداد تطبيق Gradle لأندرويد", "Android Gradle ऐप कॉन्फ़िगरेशन नहीं मिला"),
    "Executar a build Gradle real no workspace?": ("Run the real Gradle build in the workspace?", "¿Ejecutar la build Gradle real en el espacio de trabajo?", "تنفيذ بناء Gradle حقيقي في مساحة العمل؟", "कार्यस्थान में वास्तविक Gradle बिल्ड चलाएँ?"),
    "compilando projeto Android": ("building Android project", "compilando el proyecto Android", "جارٍ بناء مشروع Android", "Android प्रोजेक्ट बिल्ड हो रहा है"),
    "APK real validado": ("Real APK validated", "APK real validado", "تم التحقق من APK الحقيقي", "वास्तविक APK सत्यापित"),
    "Nenhum APK validado": ("No APK validated", "Ningún APK validado", "لم يتم التحقق من أي APK", "कोई APK सत्यापित नहीं हुआ"),
    "FERRAMENTAS DE BUILD": ("BUILD TOOLS", "HERRAMIENTAS DE COMPILACIÓN", "أدوات البناء", "बिल्ड टूल"),
    "RESULTADO DA ANÁLISE": ("ANALYSIS RESULT", "RESULTADO DEL ANÁLISIS", "نتيجة التحليل", "विश्लेषण परिणाम"),
    "Relatório OffTec PortAI": ("OffTec PortAI Report", "Informe de OffTec PortAI", "تقرير OffTec PortAI", "OffTec PortAI रिपोर्ट"),
    "Relatório de Portabilidade de Jogo": ("Game Portability Report", "Informe de portabilidad del juego", "تقرير قابلية نقل اللعبة", "गेम पोर्टेबिलिटी रिपोर्ट"),
    "Relatório de Tradução": ("Translation Report", "Informe de traducción", "تقرير الترجمة", "अनुवाद रिपोर्ट"),
    "Arquivos reconhecidos": ("Files recognized", "Archivos reconocidos", "الملفات المكتشفة", "पहचानी गई फ़ाइलें"),
    "Arquivos de texto lidos": ("Text files read", "Archivos de texto leídos", "ملفات النص المقروءة", "पढ़ी गई टेक्स्ट फ़ाइलें"),
    "Arquivos de código/configuração lidos": ("Code/configuration files read", "Archivos de código/configuración leídos", "ملفات الشيفرة/الإعدادات المقروءة", "पढ़ी गई कोड/कॉन्फ़िगरेशन फ़ाइलें"),
    "Avaliação": ("Assessment", "Evaluación", "التقييم", "मूल्यांकन"),
    "Arquivos de build": ("Build files", "Archivos de build", "ملفات البناء", "बिल्ड फ़ाइलें"),
    "Indicadores Windows": ("Windows indicators", "Indicadores de Windows", "مؤشرات Windows", "Windows संकेतक"),
    "Limitações": ("Limitations", "Limitaciones", "القيود", "सीमाएँ"),
    "Arquivos candidatos à revisão": ("Files recommended for review", "Archivos candidatos a revisión", "ملفات مقترحة للمراجعة", "समीक्षा के लिए सुझाई गई फ़ाइलें"),
    "Plano de portabilidade": ("Portability plan", "Plan de portabilidad", "خطة قابلية النقل", "पोर्टेबिलिटी योजना"),
    "Host de build indicado": ("Suggested build host", "Host de compilación indicado", "النظام المضيف المقترح للبناء", "सुझाया गया बिल्ड होस्ट"),
    "Dependências e plugins": ("Dependencies and plugins", "Dependencias y complementos", "التبعيات والإضافات", "निर्भरताएँ और प्लगइन्स"),
    "Controles e compatibilidade": ("Controls and compatibility", "Controles y compatibilidad", "عناصر التحكم والتوافق", "नियंत्रण और संगतता"),
    "Linguagens": ("Languages", "Lenguajes", "اللغات", "भाषाएँ"),
    "Linguagens e arquivos": ("Languages and files", "Lenguajes y archivos", "اللغات والملفات", "भाषाएँ और फ़ाइलें"),
    "Quantidade": ("Count", "Cantidad", "العدد", "संख्या"),
    "Possíveis obstáculos à portabilidade": ("Possible portability obstacles", "Posibles obstáculos a la portabilidad", "عقبات محتملة أمام قابلية النقل", "पोर्टेबिलिटी की संभावित बाधाएँ"),
    "Indicador": ("Indicator", "Indicador", "المؤشر", "संकेतक"),
    "Markdown:": ("Markdown:", "Markdown:", "Markdown:", "Markdown:"),
    "JSON:": ("JSON:", "JSON:", "JSON:", "JSON:"),
    "Nenhum relatório ainda.": ("No reports yet.", "Aún no hay informes.", "لا توجد تقارير بعد.", "अभी कोई रिपोर्ट नहीं।"),
    "OffTec PortAI encerrado. Até a próxima!": ("OffTec PortAI closed. See you next time!", "OffTec PortAI ha terminado. ¡Hasta la próxima!", "تم إغلاق OffTec PortAI. إلى اللقاء!", "OffTec PortAI बंद हुआ। फिर मिलेंगे!"),
    "Operação interrompida pelo usuário.": ("Operation interrupted by user.", "Operación interrumpida por el usuario.", "أوقف المستخدم العملية.", "उपयोगकर्ता ने प्रक्रिया रोक दी।"),
    "Erro inesperado": ("Unexpected error", "Error inesperado", "خطأ غير متوقع", "अनपेक्षित त्रुटि"),
    "Idioma da interface": ("Interface language", "Idioma de la interfaz", "لغة الواجهة", "इंटरफ़ेस भाषा"),
    "Selecione o idioma da interface": ("Select the interface language", "Seleccione el idioma de la interfaz", "اختر لغة الواجهة", "इंटरफ़ेस भाषा चुनें"),
    "Idioma salvo": ("Language saved", "Idioma guardado", "تم حفظ اللغة", "भाषा सहेजी गई"),
    "Configurações": ("Settings", "Configuración", "الإعدادات", "सेटिंग्स"),
    "Idioma": ("Language", "Idioma", "اللغة", "भाषा"),
    "Voltar": ("Back", "Volver", "رجوع", "वापस"),
    "Escolha uma opção": ("Choose an option", "Elija una opción", "اختر خيارًا", "एक विकल्प चुनें"),
    "Opção inválida.": ("Invalid option.", "Opción no válida.", "خيار غير صالح.", "अमान्य विकल्प।"),
}

_CATALOGS = {
    locale: {source: translations[index] for source, translations in _ROWS.items()}
    for index, locale in enumerate(("en", "es", "ar", "hi"))
}
_locale = "pt-BR"
_TECHNICAL_RE = re.compile(r"\b(?:AI Game Recreation Engine|Universal Translation Engine|Codex CLI|GameMaker|Apktool|JADX|Termux)\b")


def set_config_path(path: Path) -> None:
    """Override settings path; primarily useful for isolated tests."""
    global CONFIG_PATH
    CONFIG_PATH = Path(path)


def load_locale() -> str:
    global _locale
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        choice = data.get("interface_language", "pt-BR")
        _locale = choice if choice in LOCALES else "pt-BR"
    except (OSError, ValueError, AttributeError):
        _locale = "pt-BR"
    return _locale


def save_locale(locale: str) -> None:
    global _locale
    if locale not in LOCALES:
        raise ValueError(f"Unsupported interface language: {locale}")
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {}
    try:
        current = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if isinstance(current, dict):
            payload.update(current)
    except (OSError, ValueError):
        pass
    payload["interface_language"] = locale
    temp_path = CONFIG_PATH.with_suffix(CONFIG_PATH.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(CONFIG_PATH)
    _locale = locale


def get_locale() -> str:
    return _locale


def translate_text(value: str, locale: str | None = None) -> str:
    """Translate known UI phrases while leaving arbitrary paths/IDs intact."""
    target = locale or _locale
    if target == "pt-BR" or target not in _CATALOGS:
        return value
    catalog = _CATALOGS[target]
    technical: list[str] = []

    def protect(match: re.Match[str]) -> str:
        marker = f"\x00PORTAI_TECH_{len(technical)}\x00"
        technical.append(match.group(0))
        return marker

    value = _TECHNICAL_RE.sub(protect, value)
    protected_pattern = re.compile(
        r"(`[^`]*`|/[A-Za-z0-9_.~%+@/-]+|[A-Za-z]:\\[^\s,;)]*|"
        r"(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+|\b[A-Za-z_][A-Za-z0-9_]*_[A-Za-z0-9_]+\b)"
    )
    parts = protected_pattern.split(value)
    for index, part in enumerate(parts):
        if not part or protected_pattern.fullmatch(part):
            continue
        for source in sorted(catalog, key=len, reverse=True):
            if source in part:
                translated = catalog[source]
                if target == "ar":
                    # Unicode bidi isolates improve Arabic phrase ordering in terminals
                    # with bidi support while keeping adjacent paths/IDs isolated.
                    translated = f"\u2068{translated}\u2069"
                part = part.replace(source, translated)
        parts[index] = part
    value = "".join(parts)
    for index, original in enumerate(technical):
        value = value.replace(f"\x00PORTAI_TECH_{index}\x00", original)
    return value


def tr(message: str) -> str:
    return translate_text(message)


def ask_prompt(prompt: str, **kwargs: Any) -> str:
    from rich.prompt import Prompt
    return Prompt.ask(tr(prompt), **kwargs)


def ask_confirm(prompt: str, **kwargs: Any) -> bool:
    from rich.prompt import Confirm
    return Confirm.ask(tr(prompt), **kwargs)


def locale_choices() -> list[str]:
    return [f"{number}. {LOCALE_NAMES[locale]} [{locale}]" for number, locale in enumerate(LOCALES, 1)]


def locale_from_choice(choice: str) -> str:
    number = int(choice.split(".", 1)[0])
    if number < 1 or number > len(LOCALES):
        raise ValueError("Invalid interface language selection")
    return LOCALES[number - 1]


load_locale()
