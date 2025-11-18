from django.db import migrations


def forwards(apps, schema_editor):
    Room = apps.get_model('accounts', 'Room')
    # Define mapping here (cannot import from models in migrations)
    category_map = {
        1: "채소/과일",
        2: "육류/유제품",
        3: "해산물",
        4: "쌀/곡류",
        5: "냉장/냉동/인스턴트",
        6: "음료/주류",
        7: "건강식품",
        8: "반려동물 용품",
        9: "문구/패션/생활",
        10: "기타",
    }
    name_to_code = {v: k for k, v in category_map.items()}
    for room in Room.objects.all():
        cats = room.categories or []
        changed = False
        new_cats = []
        for c in cats:
            if isinstance(c, int):
                new_cats.append(c)
            else:
                code = None
                # Try numeric string first
                try:
                    code = int(str(c))
                except Exception:
                    code = name_to_code.get(str(c))
                if code in category_map:
                    new_cats.append(code)
                    changed = True
        if changed:
            room.categories = new_cats
            room.save(update_fields=['categories'])


def backwards(apps, schema_editor):
    Room = apps.get_model('accounts', 'Room')
    category_map = {
        1: "채소/과일",
        2: "육류/유제품",
        3: "해산물",
        4: "쌀/곡류",
        5: "냉장/냉동/인스턴트",
        6: "음료/주류",
        7: "건강식품",
        8: "반려동물 용품",
        9: "문구/패션/생활",
        10: "기타",
    }
    for room in Room.objects.all():
        cats = room.categories or []
        changed = False
        new_cats = []
        for c in cats:
            if isinstance(c, int):
                name = category_map.get(c)
                if name:
                    new_cats.append(name)
                    changed = True
            else:
                new_cats.append(c)
        if changed:
            room.categories = new_cats
            room.save(update_fields=['categories'])


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0008_room_categories_json'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]


