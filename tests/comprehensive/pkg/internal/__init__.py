class InternalClass:
    def __init__(self, a: int, b: str) -> None:
        self.a = a
        self._b = b

    def public_method(self):
        pass

    def _private_method(self):
        pass


class ExposedClass2:
    def __init__(self):
        pass

    def public_method(self):
        pass

    def _private_method(self):
        pass


class ExposedClass3:
    def __init__(self):
        pass

    def public_method(self) -> "ExposedClass4":
        return ExposedClass4()

    def _private_method(self):
        pass


class ExposedClass4:
    def __init__(self):
        pass

    def public_method(self):
        pass

    def _private_method(self):
        pass


class ExposedClass5:
    def __init__(self):
        pass

    def public_method(self):
        pass

    def _private_method(self):
        pass


class ExposedClass6:
    def public_method(self):
        pass

    def _private_method(self):
        pass


class ExposedClass7:
    def public_method(self):
        pass

    def _private_method(self):
        pass


class ExposedClass8:
    def public_method(self):
        pass

    def _private_method(self):
        pass


class ExposedClass9:
    def public_method(self):
        pass

    def _private_method(self):
        pass


class ExposedClass10:
    def public_method(self):
        pass

    def _private_method(self):
        pass


class ExposedClass11:
    def public_method(self):
        pass

    def _private_method(self):
        pass
