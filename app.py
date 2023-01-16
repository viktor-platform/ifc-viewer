import random
from pathlib import Path
from random import randint
from tempfile import NamedTemporaryFile
from typing import List, Any

import ifcopenshell
import ifcopenshell.geom as geom
from shapely import affinity, Point
from viktor import ViktorController, File, Color, geometry, UserException
from viktor.geometry import Triangle, TriangleAssembly, Material
from viktor.parametrization import ViktorParametrization, FileField, MultiSelectField, \
    LineBreak
from viktor.views import GeometryView, GeometryResult


def get_element_options(params, **kwargs) -> List[str]:
    """Get all existing geometry element types from ifc file."""
    if not params.ifc_upload:
        return []
    model = load_ifc_file_into_model(params.ifc_upload.file)
    elements = model.by_type("IfcElement")
    element_options = []
    for element in elements:
        if element.Representation:
            element_options.append(element.get_info()["type"])
    return list(set(element_options))


class Parametrization(ViktorParametrization):
    """Viktor parametrization."""
    ifc_upload = FileField("Upload model", file_types=[".ifc"], max_size=20_000_000)
    lb = LineBreak()
    element_filter = MultiSelectField("Filter elements", options=get_element_options)


class Controller(ViktorController):
    """Viktor Controller."""

    label = 'My Entity Type'
    parametrization = Parametrization

    @staticmethod
    @GeometryView("3D model of filtered elements", duration_guess=12)
    def ifc_view(params, **kwargs):
        """View 3D model of filtered elements from uploaded .ifc file."""

        # Load ifc file and set settings
        if not params.ifc_upload or not params.element_filter:
            raise UserException("Upload ifc file and select elements.")
        model = load_ifc_file_into_model(params.ifc_upload.file)
        settings = ifcopenshell.geom.settings()

        # Get geometry from selected elements
        geometry_groups = []
        selected_elements = params.element_filter
        for element_type in selected_elements:
            material = Material(
                name=element_type,
                color=get_random_color(element_type)
            )
            elements = model.by_type(element_type)
            for element in elements:

                # Create triangle assembly and assign material
                triangle_assembly = TriangleAssembly(
                    triangles=get_faces_from_ifc_element(element, settings),
                    material=material
                )
                geometry_groups.append(triangle_assembly)

        return GeometryResult(geometry_groups)


def get_faces_from_ifc_element(element, settings) -> List[Triangle]:
    """Get viktor.geometry triangular faces from ifc element geometry."""

    # Get ifc element geometry
    shape = ifcopenshell.geom.create_shape(settings, element)
    faces = shape.geometry.faces

    # Convert IfcOpenShell matrix to Shapely matrix
    matrix = shape.transformation.matrix.data
    shapely_matrix = [
        matrix[0], matrix[3], matrix[6],
        matrix[1], matrix[4], matrix[7],
        matrix[2], matrix[5], matrix[8],
        matrix[9], matrix[10], matrix[11],
    ]

    # Transform all vertices with transformation matrix
    verts = shape.geometry.verts
    grouped_verts = []
    for i in range(0, len(verts), 3):
        point = Point(verts[i], verts[i + 1], verts[i + 2])
        point = affinity.affine_transform(point, shapely_matrix)
        grouped_verts.append(geometry.Point(point.x, point.y, point.z))

    # Convert vertices of each face to triangle
    grouped_faces = []
    for i in range(0, len(faces), 3):
        triangle = Triangle(
            grouped_verts[faces[i]],
            grouped_verts[faces[i + 1]],
            grouped_verts[faces[i + 2]]
        )
        grouped_faces.append(triangle)

    return grouped_faces


def load_ifc_file_into_model(file: File) -> Any:
    """Load ifc file into ifc model object."""
    ifc_upload: File = file
    temp_file = NamedTemporaryFile(suffix='.sld', delete=False, mode='wb')
    temp_file.write(ifc_upload.getvalue_binary())
    temp_file.close()
    path = Path(temp_file.name)
    model = ifcopenshell.open(path)
    return model


def get_random_color(seed_word: str) -> Color:
    """Generate pseudo random rgb color.
    Will always return same color for same name."""
    random.seed(seed_word)
    return Color(randint(128, 220), (randint(100, 128)), randint(100, 220))
