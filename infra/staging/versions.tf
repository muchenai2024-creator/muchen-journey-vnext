terraform {
  required_version = ">= 1.11.0, < 2.0.0"

  required_providers {
    random = {
      source  = "hashicorp/random"
      version = "3.7.2"
    }
    volcenginecc = {
      source  = "volcengine/volcenginecc"
      version = "0.0.57"
    }
  }

  backend "s3" {}
}

provider "volcenginecc" {
  region = var.region_id
}
