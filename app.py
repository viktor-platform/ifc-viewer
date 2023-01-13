from viktor import ViktorController
from viktor.parametrization import ViktorParametrization


class Parametrization(ViktorParametrization):
    pass


class Controller(ViktorController):
    label = 'My Entity Type'
    parametrization = Parametrization
