# Propuesta S06, no desplegada. No ejecutar plan/apply para esta evaluación.
# S3 guardaría artefactos previamente protegidos, no originales con PII en claro.
terraform {
  required_version = ">= 1.9, < 2.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = var.region
}

variable "region" {
  description = "Región de la propuesta; validar no requiere una cuenta AWS."
  type        = string
  default     = "us-east-1"
}

variable "bucket_name" {
  description = "Nombre globalmente único, obligatorio antes de cualquier uso fuera de esta prueba."
  type        = string
  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$", var.bucket_name))
    error_message = "Usar entre 3 y 63 caracteres minúsculos, números o guiones."
  }
}

variable "name_prefix" {
  description = "Prefijo de nombres IAM de esta propuesta."
  type        = string
  default     = "bia-evaluation"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,39}$", var.name_prefix))
    error_message = "Usar entre 3 y 40 caracteres minúsculos, números o guiones."
  }
}

variable "trusted_role_arns" {
  description = "Roles existentes autorizados a asumir cada función; no usuarios, root ni comodines."
  type = object({
    ingesta  = string
    analista = string
    auditor  = string
  })
  validation {
    condition = length(distinct(values(var.trusted_role_arns))) == 3 && alltrue([
      for arn in values(var.trusted_role_arns) :
      can(regex("^arn:aws:iam::[0-9]{12}:role/[A-Za-z0-9_+=,.@/-]+$", arn))
    ])
    error_message = "Usar tres ARNs distintos de roles IAM explícitos, sin comodines."
  }
}

variable "key_admin_role_arn" {
  description = "Rol administrador existente de KMS, separado de los roles operativos creados aquí."
  type        = string
  validation {
    condition = can(regex("^arn:aws:iam::[0-9]{12}:role/[A-Za-z0-9_+=,.@/-]+$", var.key_admin_role_arn)) && !contains(
      values(var.trusted_role_arns), var.key_admin_role_arn
    )
    error_message = "Indicar el ARN explícito de un rol administrador IAM, sin root ni comodines."
  }
}

locals {
  # Equivalencia de responsabilidades, no sustitución de los permisos SQL.
  access = {
    ingesta  = { read = ["protected/"], write = ["protected/", "analytics/", "audit/"] }
    analista = { read = ["analytics/"], write = [] }
    auditor  = { read = ["audit/"], write = [] }
  }
  kms_access = merge(
    { for name, access in local.access : "${title(name)}Read" => {
      role = name, actions = ["kms:Decrypt"], prefixes = access.read
    } },
    { for name, access in local.access : "${title(name)}Write" => {
      role = name, actions = ["kms:GenerateDataKey"], prefixes = access.write
    } if length(access.write) > 0 }
  )
  kms_admin_actions = [
    "kms:DescribeKey", "kms:GetKeyPolicy", "kms:PutKeyPolicy", "kms:UpdateKeyDescription",
    "kms:EnableKey", "kms:DisableKey", "kms:EnableKeyRotation", "kms:GetKeyRotationStatus",
    "kms:ScheduleKeyDeletion", "kms:CancelKeyDeletion", "kms:TagResource", "kms:UntagResource",
    "kms:ListResourceTags"
  ]
}

resource "aws_iam_role" "data" {
  for_each = local.access
  name     = "${var.name_prefix}-${each.key}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { AWS = var.trusted_role_arns[each.key] }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_s3_bucket" "data" {
  bucket        = var.bucket_name
  force_destroy = false
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_public_access_block" "data" {
  bucket                  = aws_s3_bucket.data.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "data" {
  bucket = aws_s3_bucket.data.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_versioning" "data" {
  bucket = aws_s3_bucket.data.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_kms_key" "data" {
  description             = "S06: cifrado S3; no sustituye Fernet ni almacena su llave."
  enable_key_rotation     = true
  deletion_window_in_days = 30
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat([
      {
        Sid       = "SeparateKeyAdministration"
        Effect    = "Allow"
        Principal = { AWS = var.key_admin_role_arn }
        Action    = local.kms_admin_actions
        # En una key policy, * significa exclusivamente esta llave.
        Resource = "*"
      }
      ], [for name, access in local.kms_access : {
        Sid       = "S3Use${name}"
        Effect    = "Allow"
        Principal = { AWS = aws_iam_role.data[access.role].arn }
        Action    = access.actions
        Resource  = "*"
        Condition = {
          StringEquals = { "kms:ViaService" = "s3.${var.region}.amazonaws.com" }
          StringLike = {
            "kms:EncryptionContext:aws:s3:arn" = [
              for prefix in access.prefixes : "${aws_s3_bucket.data.arn}/${prefix}*"
            ]
          }
        }
    }])
  })
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data" {
  bucket = aws_s3_bucket.data.id
  rule {
    # El contexto por objeto permite separar prefijos también en KMS.
    bucket_key_enabled = false
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.data.arn
    }
  }
}

resource "aws_s3_bucket_policy" "data" {
  bucket = aws_s3_bucket.data.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "DenyInsecureTransport"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:*"
        Resource  = [aws_s3_bucket.data.arn, "${aws_s3_bucket.data.arn}/*"]
        Condition = { Bool = { "aws:SecureTransport" = "false" } }
      },
      {
        Sid       = "RequireKMSHeader"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:PutObject"
        Resource  = "${aws_s3_bucket.data.arn}/*"
        Condition = { StringNotEquals = { "s3:x-amz-server-side-encryption" = "aws:kms" } }
      },
      {
        Sid       = "RequireExactKeyHeader"
        Effect    = "Deny"
        Principal = "*"
        Action    = "s3:PutObject"
        Resource  = "${aws_s3_bucket.data.arn}/*"
        Condition = { StringNotEquals = { "s3:x-amz-server-side-encryption-aws-kms-key-id" = aws_kms_key.data.arn } }
      }
    ]
  })
}

resource "aws_iam_role_policy" "data" {
  for_each = local.access
  role     = aws_iam_role.data[each.key].id
  name     = "${var.name_prefix}-prefix-access"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat([
      {
        Sid      = "ListAllowedPrefixes"
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = aws_s3_bucket.data.arn
        Condition = { StringLike = {
          "s3:prefix" = [for prefix in distinct(concat(each.value.read, each.value.write)) : "${prefix}*"]
        } }
      },
      {
        Sid      = "ReadAllowedObjects"
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = [for prefix in each.value.read : "${aws_s3_bucket.data.arn}/${prefix}*"]
      }
      ], [for name, access in local.kms_access : {
        Sid      = "UseOnlyThisKey${name}"
        Effect   = "Allow"
        Action   = access.actions
        Resource = aws_kms_key.data.arn
        Condition = {
          StringEquals = { "kms:ViaService" = "s3.${var.region}.amazonaws.com" }
          StringLike = {
            "kms:EncryptionContext:aws:s3:arn" = [
              for prefix in access.prefixes : "${aws_s3_bucket.data.arn}/${prefix}*"
            ]
          }
        }
      } if access.role == each.key], length(each.value.write) == 0 ? [] : [{
        Sid      = "WriteAllowedObjects"
        Effect   = "Allow"
        Action   = ["s3:PutObject"]
        Resource = [for prefix in each.value.write : "${aws_s3_bucket.data.arn}/${prefix}*"]
    }])
  })
}
