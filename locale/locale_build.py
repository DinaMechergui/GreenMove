"""Génère locale/{en,ar}/LC_MESSAGES/django.po et .mo pour les chaînes EcoPlanner/accounts.
(msgfmt/gettext n'est pas requis : on utilise polib.) Usage : python locale_build.py
"""
import os
import polib

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', '..')
BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

# fr : (en, ar)
T = {
    "Votre semaine optimisée : moins de CO₂, du temps et de l'argent gagnés.": (
        "Your optimised week: less CO₂, time and money saved.",
        "أسبوعك المحسّن: انبعاثات أقل ووقت ومال أوفر."),
    "Pluie prévue": ("Rain expected", "أمطار متوقعة"),
    "Export .ics": ("Export .ics", "تصدير .ics"),
    "Rapport PDF": ("PDF report", "تقرير PDF"),
    "Recevoir par e-mail": ("Send by e-mail", "إرسال بالبريد"),
    "Mes données": ("My data", "بياناتي"),
    "Type d'utilisateur": ("User type", "نوع المستخدم"),
    "CO₂ économisé / semaine": ("CO₂ saved / week", "ثاني أكسيد الكربون الموفَّر / أسبوع"),
    "vs tout en voiture": ("vs all by car", "مقابل السيارة فقط"),
    "Budget carbone du mois": ("Monthly carbon budget", "الميزانية الكربونية للشهر"),
    "Projection": ("Projection", "التوقع"),
    "Si vous suivez ce plan 1 an": ("If you follow this plan for 1 year", "إذا اتبعت هذه الخطة لمدة سنة"),
    "arbres": ("trees", "أشجار"),
    "Plan de la semaine": ("Weekly plan", "خطة الأسبوع"),
    "Temps": ("Time", "الوقت"),
    "Coût": ("Cost", "التكلفة"),
    "Confort": ("Comfort", "الراحة"),
    "Météo auto": ("Auto weather", "طقس تلقائي"),
    "Pluie": ("Rain", "مطر"),
    "Beau temps": ("Fine weather", "طقس صحو"),
    "Recalculer": ("Recalculate", "إعادة الحساب"),
    "Partir à": ("Leave at", "المغادرة عند"),
    "arriver": ("arrive", "الوصول"),
    "Supprimer": ("Delete", "حذف"),
    "Aucun trajet habituel : ajoutez-en ci-dessous ou importez un calendrier .ics.": (
        "No usual trips: add some below or import an .ics calendar.",
        "لا توجد رحلات معتادة: أضف رحلات أدناه أو استورد تقويم .ics."),
    "Explications": ("Explanations", "تفسيرات"),
    "Ajouter un trajet habituel": ("Add a usual trip", "إضافة رحلة معتادة"),
    "Cours, réunion…": ("Class, meeting…", "درس، اجتماع…"),
    "Importer .ics": ("Import .ics", "استيراد .ics"),
    "CO₂ par semaine (8 dernières)": ("CO₂ per week (last 8)", "ثاني أكسيد الكربون أسبوعيًا (آخر 8)"),
    "CO₂ par jour de la semaine": ("CO₂ per weekday", "ثاني أكسيد الكربون حسب اليوم"),
    "Heures de pointe": ("Peak hours", "ساعات الذروة"),
    "Économies cumulées (simulateur)": ("Cumulative savings (simulator)", "المدخرات التراكمية (المحاكي)"),
    "Lun": ("Mon", "إثن"), "Mar": ("Tue", "ثلا"), "Mer": ("Wed", "أرب"), "Jeu": ("Thu", "خمي"),
    "Ven": ("Fri", "جمع"), "Sam": ("Sat", "سبت"), "Dim": ("Sun", "أحد"),
    "ou": ("or", "أو"),
    "Continuer avec Google": ("Continue with Google", "المتابعة مع Google"),
    "%(day)s : prenez %(mode)s pour « %(label)s » (%(min)s min, %(co2)s kg de CO₂, %(cost)s TND). "
    "Partez à %(leave)s pour arriver à %(arrival)s.": (
        "%(day)s: take %(mode)s for “%(label)s” (%(min)s min, %(co2)s kg CO₂, %(cost)s TND). "
        "Leave at %(leave)s to arrive at %(arrival)s.",
        "%(day)s: استخدم %(mode)s لـ «%(label)s» (%(min)s د، %(co2)s كغ CO₂، %(cost)s دينار). "
        "غادر عند %(leave)s للوصول عند %(arrival)s."),
    "Vous évitez %(kg)s kg de CO₂ par rapport à la voiture.": (
        "You avoid %(kg)s kg of CO₂ compared with driving.",
        "تتجنب %(kg)s كغ من CO₂ مقارنة بالسيارة."),
    "Votre plan évite %(kg)s kg de CO₂ cette semaine par rapport à un usage exclusif de la voiture.": (
        "Your plan avoids %(kg)s kg of CO₂ this week compared with using only the car.",
        "تتجنب خطتك %(kg)s كغ من CO₂ هذا الأسبوع مقارنة باستخدام السيارة فقط."),
}


def build(lang, idx):
    po = polib.POFile()
    po.metadata = {
        'Content-Type': 'text/plain; charset=UTF-8', 'Language': lang,
        'MIME-Version': '1.0', 'Content-Transfer-Encoding': '8bit',
        'Plural-Forms': 'nplurals=2; plural=(n != 1);' if lang == 'en'
        else 'nplurals=6; plural=n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 : n%100>=11 ? 4 : 5;',
    }
    for fr, tr in T.items():
        po.append(polib.POEntry(msgid=fr, msgstr=tr[idx], flags=['python-format'] if '%(' in fr else []))
    d = os.path.join(BASE, 'locale', lang, 'LC_MESSAGES')
    os.makedirs(d, exist_ok=True)
    po.save(os.path.join(d, 'django.po'))
    po.save_as_mofile(os.path.join(d, 'django.mo'))
    print('written', d)


if __name__ == '__main__':
    build('en', 0)
    build('ar', 1)
