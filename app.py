import random
from pathlib import Path
from random import randint
from tempfile import NamedTemporaryFile
from typing import Any, List

import ifcopenshell
import ifcopenshell.geom
from shapely import Point, affinity
from viktor import Color, File, UserException, ViktorController, geometry
from viktor.geometry import Material, Triangle, TriangleAssembly
from viktor.parametrization import (
    BooleanField,
    DownloadButton,
    FileField,
    LineBreak,
    MultiSelectField,
    Text,
    ViktorParametrization,
)
from viktor.result import DownloadResult
from viktor.views import GeometryResult, GeometryView


def get_element_options(params, **kwargs) -> List[str]:
    """Get all existing geometry element types from ifc file."""
    if not params.ifc_upload and not params.get_sample_ifc_toggle:
        return []
    if params.get_sample_ifc_toggle:
        params.sample_ifc = File.from_path(
            Path(__file__).parent / "AC20-FZK-Haus (Sample IFC).ifc"
        )
        model = load_ifc_file_into_model(params.sample_ifc)
    else:
        model = load_ifc_file_into_model(params.ifc_upload.file)
    elements = model.by_type("IfcElement")
    element_options = []
    for element in elements:
        if element.Representation:
            element_options.append(element.get_info()["type"])
    return list(set(element_options))


class Parametrization(ViktorParametrization):
    """Viktor parametrization."""

    text1 = Text(
        """
# Welcome to the ifc-viewer app!

This is a sample app demonstrating how to import and view IFC files. 
The IFC filetype (.ifc) is an international standard to import and 
export building objects and their properties. 
Most BIM-software packages allow you to import and export IFC files. 
With this application we want to show how to handle 
IFC files in a Viktor application. 
The source code of this application can be found on 
[github](https://github.com/viktor-platform/ifc-viewer).

## File upload
Make sure that your file contains IfcElements with a geometry representation. 
The app is tested with IFC 4 files. For reference, check out some 
[example files](https://www.ifcwiki.org/index.php?title=KIT_IFC_Examples).
        """
    )

    ifc_upload = FileField(
        "Upload model",
        file_types=[".ifc"],
        max_size=20_000_000,
    )

    get_sample_ifc_toggle = BooleanField(
        "Use sample IFC File",
        default=False,
        flex=30,
    )

    lb = LineBreak()
    text2 = Text(
        """
## Element filtering
Select which elements to preview. 
Only elements existing in the IFC file can be selected. 
Geometry of selected elements will be shown in the 3D viewer.
        """
    )
    element_filter = MultiSelectField(
        "Filter elements",
        options=get_element_options,
    )

    lb2 = LineBreak()
    text3 = Text(
        """
## Download
Only selected elements will be downloaded, this allows for easy removal of any of the elements
        """
    )
    download = DownloadButton(
        "Download",
        method="download_file",
    )


class Controller(ViktorController):
    """Viktor Controller."""

    label = "My Entity Type"
    parametrization = Parametrization

    def download_file(self, params, **kwargs):
        if params.get_sample_ifc_toggle == True:
            params.sample_ifc = File.from_path(
                Path(__file__).parent / "AC20-FZK-Haus (Sample IFC).ifc"
            )
            model = load_ifc_file_into_model(params.sample_ifc)
        else:
            model = load_ifc_file_into_model(params.ifc_upload.file)
        # remove all other parts from the ifc file which are not viewed
        for element in model.by_type("IfcElement"):
            if element.get_info()["type"] not in params.element_filter:
                model.remove(element)
        # part where we save the model as seen in the viewer
        temp_file = NamedTemporaryFile(suffix=".ifc", delete=False, mode="wb")
        model.write(str(Path(temp_file.name)))
        temp_file.close()
        path_out = Path(temp_file.name)
        return DownloadResult(path_out.read_bytes(), "filtered_elements.ifc")

    @staticmethod
    @GeometryView("3D model of filtered elements", duration_guess=12)
    def ifc_view(params, **kwargs):
        """View 3D model of filtered elements from uploaded .ifc file."""

        # Load ifc file and set settings
        if not params.element_filter and params.get_sample_ifc_toggle == False:
            raise UserException("Upload ifc file and select elements.")
        if params.get_sample_ifc_toggle == True:
            params.sample_ifc = File.from_path(
                Path(__file__).parent / "AC20-FZK-Haus (Sample IFC).ifc"
            )
            model = load_ifc_file_into_model(params.sample_ifc)
        else:
            model = load_ifc_file_into_model(params.ifc_upload.file)
        settings = ifcopenshell.geom.settings()

        # Get geometry from selected elements
        geometry_groups = []
        selected_elements = params.element_filter
        for element_type in selected_elements:
            material = Material(name=element_type, color=get_random_color(element_type))
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
        matrix[0],
        matrix[3],
        matrix[6],
        matrix[1],
        matrix[4],
        matrix[7],
        matrix[2],
        matrix[5],
        matrix[8],
        matrix[9],
        matrix[10],
        matrix[11],
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
            grouped_verts[faces[i + 2]],
        )
        grouped_faces.append(triangle)

    return grouped_faces


def load_ifc_file_into_model(file: File) -> Any:
    """Load ifc file into ifc model object."""
    ifc_upload: File = file
    temp_file = NamedTemporaryFile(suffix=".sld", delete=False, mode="wb")
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
