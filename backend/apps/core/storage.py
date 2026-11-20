from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction


def _is_stored(name):
    return bool(
        name
        and name != settings.SAM_DEFAULT_PROFILE_IMAGE
        and not name.startswith(("http://", "https://", "/"))
    )


def save_image(processed, folder):
    name = f"{folder.strip('/')}/{processed.random_name()}"
    return default_storage.save(name, ContentFile(processed.content))


def delete_stored_image(name):
    if _is_stored(name):
        default_storage.delete(name)


def apply_image_changes(instance, changes, *, folder, save=True):
    """Aplica trocas e remoções de imagem em colunas de caminho.

    `changes` mapeia o nome do campo para um ProcessedImage (substitui) ou
    None (remove). Arquivos substituídos só são apagados após o commit.
    """
    old_names = []
    new_names = []

    try:
        for field, processed in changes.items():
            old_names.append(getattr(instance, field))
            if processed is None:
                setattr(instance, field, None)
            else:
                name = save_image(processed, folder)
                new_names.append(name)
                setattr(instance, field, name)

        if save and changes:
            instance.save(update_fields=list(changes))
    except Exception:
        for name in new_names:
            delete_stored_image(name)
        raise

    transaction.on_commit(lambda: [delete_stored_image(name) for name in old_names])
