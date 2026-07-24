"""Arregla tlslite dentro del ejecutable empaquetado.

`tlslite/utils/deprecations.py` hace, al construir una clase renombrada:

    frame = inspect.currentframe().f_back
    code = inspect.getframeinfo(frame).code_context
    if [line for line in code if ...]:

`code_context` es `None` cuando el interprete no puede leer el codigo fuente del
frame, que es justo lo que pasa dentro de un bundle de PyInstaller: los modulos
viajan compilados y no hay .py que leer. Iterar ese `None` lanza

    TypeError: 'NoneType' object is not iterable

Le ocurre a `Python_AES` (la implementacion de AES en Python puro), que es la que
tlslite acaba usando porque no reconoce a pycryptodomex como backend rapido.
Resultado: el handshake TLS con la camara moria con "Communication error 201
(SSL error)" solo en el .exe, nunca ejecutando desde el codigo fuente.

La solucion es hacer que `getframeinfo` devuelva siempre una lista para
`code_context`. El unico efecto de perder ese contexto es que tlslite no puede
saber si la clase se invoco por su nombre viejo o el nuevo, asi que deja de
emitir un DeprecationWarning; el comportamiento criptografico no cambia.
"""

import inspect

_original_getframeinfo = inspect.getframeinfo


def _safe_getframeinfo(frame, context=1):
    info = _original_getframeinfo(frame, context)
    if info.code_context is None:
        # Traceback es una namedtuple. Se usa _replace y no el constructor
        # posicional porque en Python 3.11+ hay un campo extra ('positions')
        # que se perderia al reconstruirla a mano.
        return info._replace(code_context=[])
    return info


inspect.getframeinfo = _safe_getframeinfo
