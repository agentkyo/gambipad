"""Tiny translation layer: English source strings, optional translations."""
from __future__ import annotations

import locale

LANGUAGES = (("", "Auto"), ("en", "English"), ("pt", "Português"))

PT = {
    # buttons
    "✕ Cross": "✕ Xis",
    "○ Circle": "○ Bolinha",
    "□ Square": "□ Quadrado",
    "△ Triangle": "△ Triângulo",
    "Touchpad click": "Clique do touchpad",
    "L3 (left stick click)": "L3 (clique do analógico esquerdo)",
    "R3 (right stick click)": "R3 (clique do analógico direito)",
    "D-pad up": "Direcional para cima",
    "D-pad down": "Direcional para baixo",
    "D-pad left": "Direcional para a esquerda",
    "D-pad right": "Direcional para a direita",
    "Touchpad left half": "Metade esquerda do touchpad",
    "Touchpad right half": "Metade direita do touchpad",
    # targets
    "Left button": "Botão esquerdo",
    "Right button": "Botão direito",
    "Middle button": "Botão do meio",
    "Wheel up": "Rolar para cima",
    "Wheel down": "Rolar para baixo",
    "Controller button": "Botão do controle",
    "Keyboard key": "Tecla do teclado",
    "Mouse": "Mouse",
    "Key": "Tecla",
    "Disabled": "Desativado",
    "Macro": "Macro",
    "Turbo": "Turbo",
    "Toggle": "Alternar",
    "Default": "Padrão",
    "Add": "Adicionar",
    "Remove selected": "Remover selecionado",
    # action dialog
    "Press button(s) / key(s)": "Apertar botão(ões) / tecla(s)",
    "Turbo (rapid fire while held)": "Turbo (repete rápido enquanto segura)",
    "Toggle (press once to hold, again to release)": "Alternar (um toque segura, outro solta)",
    "Run a macro": "Executar uma macro",
    "No macros yet. Create one in the Macros tab first.": "Ainda não há macros. Crie uma na aba Macros primeiro.",
    "Action": "Ação",
    "Sends": "Envia",
    "Speed": "Velocidade",
    "New combo": "Nova combinação",
    "Do not send the individual buttons while the combo is held": "Não enviar os botões individuais enquanto a combinação estiver segurada",
    "Pick two or more buttons that must be held together:": "Escolha dois ou mais botões que precisam ser segurados juntos:",
    # window
    "Open GambiPad": "Abrir o GambiPad",
    "Quit": "Sair",
    "Still running here in the tray. Right-click to quit.": "Continuo rodando aqui na bandeja. Clique com o botão direito para sair.",
    "Profile": "Perfil",
    "Profiles…": "Perfis…",
    "New": "Novo",
    "Duplicate": "Duplicar",
    "Delete": "Excluir",
    "Import…": "Importar…",
    "Export…": "Exportar…",
    "Show what the controller sends": "Mostrar o que o controle envia",
    "Show what the game receives": "Mostrar o que o jogo recebe",
    "Buttons": "Botões",
    "Sticks": "Analógicos",
    "red = ghost signal being ignored": "vermelho = sinal fantasma sendo ignorado",
    "Light && rumble": "Luz e vibração",
    "Touchpad": "Touchpad",
    "Diagnose": "Diagnóstico",
    "Profile name:": "Nome do perfil:",
    "A profile with this name already exists.": "Já existe um perfil com esse nome.",
    "New profile": "Novo perfil",
    "My profile": "Meu perfil",
    "Duplicate profile": "Duplicar perfil",
    "This is the only profile.": "Este é o único perfil.",
    "Delete the profile “{name}”?": "Excluir o perfil “{name}”?",
    "The language changes the next time GambiPad starts.": "O idioma muda na próxima vez que o GambiPad abrir.",
    # buttons page
    "Click a button to choose what it does. Changes apply immediately.": "Clique em um botão para escolher o que ele faz. As mudanças valem na hora.",
    "Virtual controller": "Controle virtual",
    "Xbox 360 (works everywhere)": "Xbox 360 (funciona em tudo)",
    "DualShock 4 (touchpad and motion; Windows only)": "DualShock 4 (touchpad e movimento; só no Windows)",
    "None (keyboard/mouse mappings only)": "Nenhum (só mapeamentos de teclado/mouse)",
    "Games see": "Os jogos veem",
    "Reset all buttons to default": "Voltar todos os botões ao padrão",
    # sticks page
    "Left stick": "Analógico esquerdo",
    "Right stick": "Analógico direito",
    "Dead zone": "Zona morta",
    "Full tilt reached at": "Inclinação máxima atingida em",
    "Curve (1 = linear, more = finer aim)": "Curva (1 = linear, mais = mira mais fina)",
    "Invert horizontal": "Inverter horizontal",
    "Invert vertical": "Inverter vertical",
    "Swap left and right sticks": "Trocar analógico esquerdo e direito",
    "Trigger": "Gatilho",
    "Full press reached at": "Aperto máximo atingido em",
    "Hair trigger (any press counts as a full press)": "Gatilho sensível (qualquer toque vale como aperto total)",
    # light page
    "Light bar": "Barra de luz",
    "Fixed colour": "Cor fixa",
    "Battery level (green to red)": "Nível da bateria (verde a vermelho)",
    "Rainbow": "Arco-íris",
    "Off": "Desligada",
    "Mode": "Modo",
    "Colour": "Cor",
    "Brightness": "Brilho",
    "Rumble": "Vibração",
    "Let games vibrate the controller": "Deixar os jogos vibrarem o controle",
    "Strong motor (left)": "Motor forte (esquerdo)",
    "Weak motor (right)": "Motor fraco (direito)",
    "Test": "Testar",
    # touchpad page
    "Pass through (needs the DualShock 4 virtual controller)": "Repassar ao jogo (precisa do controle virtual DualShock 4)",
    "Move the mouse pointer": "Mover o ponteiro do mouse",
    "Two buttons: left half and right half": "Dois botões: metade esquerda e metade direita",
    "Ignore touches": "Ignorar toques",
    "Pointer speed": "Velocidade do ponteiro",
    "Ignore touches that never move (clones that report a finger that is not there)": "Ignorar toques que nunca se movem (clones que informam um dedo que não está lá)",
    "Many clones have no real touch sensor: the touchpad is only a button. "
    "Watch the yellow dots on the drawing while you slide a finger to find out.": "Muitos clones não têm sensor de toque de verdade: o touchpad é só um botão. "
    "Observe os pontos amarelos no desenho enquanto desliza o dedo para descobrir.",
    # macros page
    "Macros": "Macros",
    "New macro": "Nova macro",
    "Delete macro": "Excluir macro",
    "Play once per press": "Tocar uma vez a cada aperto",
    "Repeat while the button is held": "Repetir enquanto o botão estiver segurado",
    "Repeat until the button is pressed again": "Repetir até o botão ser apertado de novo",
    "Tap": "Toque",
    "Hold down": "Segurar",
    "Release": "Soltar",
    "Wait": "Esperar",
    "Add step": "Adicionar passo",
    "Remove step": "Remover passo",
    "Move up": "Subir",
    "Move down": "Descer",
    "To use a macro, open the Buttons tab, click a button and choose “Run a macro”.": "Para usar uma macro, abra a aba Botões, clique em um botão e escolha “Executar uma macro”.",
    "A macro is a recorded sequence of presses and pauses played by one button.": "Uma macro é uma sequência de apertos e pausas disparada por um botão.",
    "Combos": "Combinações",
    "A combo fires an action when several buttons are held together.": "Uma combinação dispara uma ação quando vários botões são segurados juntos.",
    "Remove combo": "Remover combinação",
    "Macro name:": "Nome da macro:",
    "Pick at least two buttons.": "Escolha pelo menos dois botões.",
    # diagnose page
    "Ghost button test": "Teste de botões fantasmas",
    "Some clones report a second button together with the one you pressed (for example L1 also "
    "sending PS). Start the test and press every button, ONE AT A TIME, for about a second each.": "Alguns clones enviam um segundo botão junto com o que você apertou (por exemplo, o L1 enviando "
    "também o PS). Inicie o teste e aperte todos os botões, UM DE CADA VEZ, por cerca de um segundo cada.",
    "Start the test": "Iniciar o teste",
    "Apply the fix": "Aplicar a correção",
    "Active fixes": "Correções ativas",
    "While {a} is held, ignore {b}": "Enquanto {a} estiver apertado, ignorar {b}",
    "Driver log": "Registro do driver",
    "No controller connected.": "Nenhum controle conectado.",
    "all buttons seen, you can wait or keep pressing": "todos os botões detectados, pode esperar ou continuar apertando",
    "{n} s left. Still to press: {rest}": "Faltam {n} s. Ainda falta apertar: {rest}",
    "Never detected: {rest}": "Nunca detectado: {rest}",
    "Found: pressing {a} also reports {b}": "Encontrado: apertar {a} também envia {b}",
    "No new ghost buttons found.": "Nenhum botão fantasma novo encontrado.",
    # status
    "battery": "bateria",
    "Looking for a controller… plug it in.": "Procurando um controle… conecte-o.",
    "The real controller is hidden from games. If a game still sees two controllers, unplug and replug it once.": "O controle real está escondido dos jogos. Se um jogo ainda enxergar dois controles, desconecte e reconecte o cabo uma vez.",
    "keys": "teclas",
    "mouse": "mouse",
    "GambiPad is already running (look in the system tray).": "O GambiPad já está rodando (veja na bandeja do sistema).",
}

TABLES = {"pt": PT}
_current: dict[str, str] = {}


def system_language() -> str:
    try:
        code = (locale.getlocale()[0] or "").lower()
    except ValueError:
        code = ""
    return "pt" if code.startswith(("pt", "portuguese")) else "en"


def set_language(code: str | None) -> None:
    global _current
    _current = TABLES.get(code or system_language(), {})


def tr(text: str) -> str:
    return _current.get(text, text)
