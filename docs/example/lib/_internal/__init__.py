# _internal/__init__.py


class LeakedPrivate:
    def public_method(self) -> None:
        pass


class Private:
    pass
