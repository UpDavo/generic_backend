from storages.backends.s3boto3 import S3Boto3Storage


class PrivateUploadStorage(S3Boto3Storage):
    location = 'private'
    default_acl = None  # Evita errores con buckets que no permiten ACLs
    file_overwrite = False
    auto_create_bucket = True


class PublicUploadStorage(S3Boto3Storage):
    location = 'public'
    default_acl = None  # Evita errores con buckets que no permiten ACLs
    file_overwrite = False
    auto_create_bucket = True
