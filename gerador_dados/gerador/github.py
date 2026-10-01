"""Envio dos arquivos de dados para o GitHub ao final de cada execução.

Somente os arquivos da pasta de dados que realmente mudaram entram no commit
(as planilhas só são regravadas quando o conteúdo muda). Se nada mudou, nada é
enviado. Se o envio falhar (sem internet, sem credenciais, pasta fora de um
repositório git), os dados continuam salvos localmente e o próximo envio bem
sucedido leva também os commits pendentes.
"""

import subprocess
from pathlib import Path

IDENTIDADE_PADRAO = ["-c", "user.name=Gerador de dados da cantina",
                     "-c", "user.email=gerador-dados@users.noreply.github.com"]


class ErroGit(Exception):
    pass


def _git(pasta: Path, *args, checar=True) -> subprocess.CompletedProcess:
    try:
        r = subprocess.run(["git", *args], cwd=pasta, capture_output=True, text=True, timeout=300)
    except FileNotFoundError:
        raise ErroGit("git não está instalado")
    except subprocess.TimeoutExpired:
        raise ErroGit(f"git {args[0]} demorou demais")
    if checar and r.returncode != 0:
        linhas = (r.stderr or r.stdout).strip().splitlines()
        raise ErroGit(f"git {args[0]}: {linhas[0] if linhas else 'erro desconhecido'}")
    return r


def enviar_dados(pasta_dados: Path, mensagem: str, remoto: str = "origin",
                 branch: str | None = None) -> str:
    """Faz commit das alterações em `pasta_dados` e envia ao remoto. Devolve um resumo."""
    pasta_dados = pasta_dados.resolve()
    try:
        _git(pasta_dados, "rev-parse", "--show-toplevel")
    except ErroGit:
        return "a pasta de dados não está em um repositório git; arquivos mantidos só localmente"

    try:
        branch = branch or _git(pasta_dados, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        if branch == "HEAD":
            return "repositório sem branch ativa (detached HEAD); arquivos mantidos só localmente"

        # Apenas a pasta de dados entra no commit, mesmo que haja outras alterações no repositório
        _git(pasta_dados, "add", "--all", "--", ".")
        alterados = _git(pasta_dados, "diff", "--cached", "--name-only", "--", ".").stdout.split()
        if alterados:
            identidade = [] if _git(pasta_dados, "config", "user.email", checar=False).stdout.strip() \
                else IDENTIDADE_PADRAO
            _git(pasta_dados, *identidade, "commit", "-m", mensagem, "--", ".")

        remoto_existe = _git(pasta_dados, "ls-remote", "--exit-code", "--heads", remoto, branch,
                             checar=False).returncode == 0
        if remoto_existe:
            _git(pasta_dados, "fetch", remoto, branch)
            pendentes = int(_git(pasta_dados, "rev-list", "--count",
                                 f"{remoto}/{branch}..HEAD").stdout.strip())
            if pendentes == 0:
                return "nenhum arquivo de dados mudou; nada a enviar"
            rebase = _git(pasta_dados, "rebase", "--autostash", f"{remoto}/{branch}", checar=False)
            if rebase.returncode != 0:
                _git(pasta_dados, "rebase", "--abort", checar=False)
                return "conflito ao integrar alterações do GitHub; commit mantido localmente"
        _git(pasta_dados, "push", remoto, f"HEAD:refs/heads/{branch}")
    except ErroGit as e:
        return f"envio ao GitHub falhou, dados mantidos localmente: {e}"

    return f"{len(alterados)} arquivo(s) de dados enviados para {remoto}/{branch}" if alterados \
        else f"commits pendentes enviados para {remoto}/{branch}"
