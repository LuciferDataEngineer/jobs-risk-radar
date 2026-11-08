provider "docker" {}

resource "docker_network" "radar" {
  name = "jobs-risk-radar"
}

resource "docker_image" "radar" {
  name         = "jobs-risk-radar:local"
  keep_locally = true
  build {
    context    = abspath("${path.module}/../..")
    dockerfile = "Dockerfile"
  }
}
