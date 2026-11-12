
terraform {
  required_providers {
    libvirt = {
      source  = "dmacvicar/libvirt"
      version = "0.8.3"
    }
  }
}

provider "libvirt" {
  uri = "qemu:///system"
}

locals {
  vms = toset([
    "pi-g3-01",
    "pi-g3-02"
  ])
}

# Imagem base Ubuntu 24.04
resource "libvirt_volume" "ubuntu_base" {
  name   = "pi-g3-ubuntu-24.04-base.qcow2"
  pool   = "default"
  source = "https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img"
  format = "qcow2"
}

# Discos individuais das VMs
resource "libvirt_volume" "vm_disk" {
  for_each = local.vms

  name           = "${each.key}.qcow2"
  pool           = "default"
  base_volume_id = libvirt_volume.ubuntu_base.id
  format         = "qcow2"
  size           = 12 * 1024 * 1024 * 1024
}

# Configuração inicial das máquinas
resource "libvirt_cloudinit_disk" "init" {
  for_each = local.vms

  name = "${each.key}-cloudinit.iso"
  pool = "default"

  user_data = templatefile("${path.module}/cloud_init.cfg", {
    hostname = each.key
    ssh_key  = trimspace(file(pathexpand("~/.ssh/devops_lab.pub")))
  })
}

# Criação das máquinas virtuais
resource "libvirt_domain" "vm" {
  for_each = local.vms

  name   = each.key
  memory = 2048
  vcpu   = 2

  cloudinit = libvirt_cloudinit_disk.init[each.key].id

  network_interface {
    network_name   = "default"
    wait_for_lease = true
  }

  disk {
    volume_id = libvirt_volume.vm_disk[each.key].id
  }

  console {
    type        = "pty"
    target_type = "serial"
    target_port = "0"
  }
}

# Exibir os IPs das máquinas
output "ips" {
  description = "Endereços IP das VMs do PI Grupo 3"

  value = {
    for nome, vm in libvirt_domain.vm :
    nome => vm.network_interface[0].addresses
  }
}