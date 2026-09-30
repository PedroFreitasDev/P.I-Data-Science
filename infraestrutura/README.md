# P.I-Data-Science

Projeto acadêmico de **DevOps, Infraestrutura Privada e Simulação de Dados**.

Utiliza **OpenTofu, Libvirt/QEMU, cloud-init, Ansible, SSH e Python** para provisionar uma máquina virtual, configurar o ambiente e executar um simulador de dados.

## Estrutura

```text
P.I-Data-Science/
├── DOCS/
├── infraestrutura/
│   ├── main.tf
│   ├── cloud_init.cfg
│   └── ansible/
│       ├── inventory.ini
│       └── playbook.yml
├── gerador_dados/
│   ├── gerar_dados.py
│   ├── requirements.txt
│   └── gerador/
├── .gitignore
└── README.md
```

## Tecnologias

* Ubuntu Server
* OpenTofu
* Libvirt / QEMU
* cloud-init
* Ansible
* SSH
* Python 3
* OpenPyXL

## Pré-requisitos

Linux com virtualização habilitada e os seguintes programas:

```bash
sudo apt update
sudo apt install -y git qemu-kvm libvirt-daemon-system libvirt-clients python3 python3-pip python3-venv ansible
```

Adicionar o usuário aos grupos:

```bash
sudo usermod -aG libvirt $USER
sudo usermod -aG kvm $USER
```

Também é necessário ter o **OpenTofu** instalado.

## 1. Clonar o projeto

```bash
git clone https://github.com/PedroFreitasDev/P.I-Data-Science.git
cd P.I-Data-Science
```

## 2. Configurar SSH

Criar a chave utilizada pelas VMs:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/devops_lab
```

A chave privada não deve ser enviada ao GitHub.

## 3. Provisionar a infraestrutura

```bash
cd infraestrutura
tofu init
tofu plan
tofu apply
```

O OpenTofu cria as VMs `devops-1` e `devops-2` utilizando Libvirt/QEMU e cloud-init.

Verificar as VMs:

```bash
sudo virsh list
tofu output
```

## 4. Testar SSH

Utilize o IP da VM:

```bash
ssh -i ~/.ssh/devops_lab aluno@IP_DA_VM
```

## 5. Configurar com Ansible

```bash
cd infraestrutura/ansible
ansible -i inventory.ini servidores -m ping
ansible-playbook -i inventory.ini playbook.yml
```

O playbook instala Python e dependências, cria os diretórios do projeto e configura o ambiente virtual.

Caso o IP das VMs tenha mudado, atualize o `inventory.ini`.

## 6. Enviar e executar o simulador

A partir da raiz do projeto:

```bash
scp -i ~/.ssh/devops_lab -r gerador_dados aluno@IP_DA_VM:/home/aluno/projeto-data-science/
```

Conecte-se à VM:

```bash
ssh -i ~/.ssh/devops_lab aluno@IP_DA_VM
```

Execute:

```bash
cd /home/aluno/projeto-data-science/gerador_dados
.venv/bin/python gerar_dados.py
```

Os dados são armazenados em:

```text
saida/
```

Para verificar:

```bash
find saida -maxdepth 2 -type f | sort
```

O arquivo `saida/estado.json` mantém o estado das execuções.

## Fluxo

```text
GitHub
  ↓
OpenTofu
  ↓
Libvirt / QEMU
  ↓
VM + cloud-init
  ↓
SSH
  ↓
Ansible
  ↓
Ambiente Python
  ↓
SCP
  ↓
Simulador
  ↓
Dados gerados
```

## Observações

* O simulador e o playbook utilizam principalmente a `devops-1`.
* Os IPs das VMs podem mudar após recriação.
* Não versionar chaves SSH privadas, `terraform.tfstate`, arquivos `.qcow2` ou dados gerados.
* O projeto também pode executar o simulador diretamente no computador, utilizando Python e `requirements.txt`.
