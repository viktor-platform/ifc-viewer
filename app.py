import time
import random
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, List
import trimesh
import ifcopenshell
import ifcopenshell.geom
from munch import Munch
from viktor import Color, File, ViktorController
from viktor.parametrization import (
    BooleanField,
    DownloadButton,
    FileField,
    LineBreak,
    MultiSelectField,
    Text,
    IsFalse,
    Lookup,
    ViktorParametrization,
)
from viktor.result import DownloadResult
from viktor.views import GeometryResult, GeometryView, WebView, WebResult
from viktor.core import progress_message


PROGRESS_MESSAGE_DELAY = 3  # seconds


def _use_correct_file(params: Munch):
    if params.get_sample_ifc_toggle is True:
        params.use_file = File.from_path(Path(__file__).parent / "AC20-FZK-Haus (Sample IFC).ifc")
    else:
        params.use_file = params.ifc_upload.file
    return params.use_file


def _load_ifc_file(params: Munch) -> Any:
    """Load ifc file into ifc model object."""
    ifc_upload = _use_correct_file(params)
    path = ifc_upload.copy().source
    model = ifcopenshell.open(path)
    return model


def get_element_options(params, **kwargs) -> List[str]:
    """Get all existing geometry element types from ifc file."""
    if not params.ifc_upload and not params.get_sample_ifc_toggle:
        return []
    model = _load_ifc_file(params)
    elements = model.by_type("IfcElement")
    element_options = []
    for element in elements:
        if element.Representation:
            element_options.append(element.get_info()["type"])
    return list(set(element_options))


def get_random_color(seed_word: str) -> Color:
    """Will always return same color for same name."""
    random.seed(seed_word)
    color_list = [
        (59, 89, 152),
        (139, 157, 195),
        (223, 227, 238),
        (247, 247, 247),
        (255, 220, 115),
        (55, 186, 186),
    ]
    chosen_color = random.choice(color_list)
    return Color(*chosen_color)


class Parametrization(ViktorParametrization):
    """Viktor parametrization."""

    text1 = Text(
        """
# Welcome to the ifc-viewer app!

This is a sample app demonstrating how to import, view, seperate and download the elements of an IFC files. 
The IFC filetype (.ifc) is an international standard to import and 
export building objects and their properties. 
Most BIM-software packages allow you to import and export IFC files. 
With this application we want to show that a VIKTOR application can handle and transform your .ifc file. 
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
        visible=IsFalse(Lookup("get_sample_ifc_toggle")),
        max_size=20_000_000,
    )

    get_sample_ifc_toggle = BooleanField(
        "Use sample IFC File",
        default=True,
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
Only selected elements will be downloaded, this allows for easy removal 
of any of the elements that are not needed. This is a useful application 
for when a colleague may want to perform some analysis on structural elements 
only.
        """
    )
    download = DownloadButton(
        "Download",
        method="download_file",
        longpoll=True,
    )


class Controller(ViktorController):
    """Viktor Controller."""

    label = "My Entity Type"
    parametrization = Parametrization

    @staticmethod
    def download_file(params: Munch, **kwargs):
        progress_message("Load IFC file...")
        model = _load_ifc_file(params)
        # initialize the variables responsible for progress message delays
        delta_time = PROGRESS_MESSAGE_DELAY + 1
        start = time.time()
        # remove all other parts from the ifc file which are not viewed
        for element in model.by_type("IfcElement"):
            if element.get_info()["type"] not in params.element_filter:
                if delta_time > PROGRESS_MESSAGE_DELAY:
                    # the logic of progress message delays is implemented to avoid cases where the progress messages
                    # flood the progress message queue
                    start = time.time()
                    progress_message(f"Removing element: {element.get_info()['type']}")
                model.remove(element)
            delta_time = time.time() - start
        # part where we save the model as seen in the viewer
        progress_message("Save file...")
        temp_file = NamedTemporaryFile(suffix=".ifc", delete=False, mode="wb")
        model.write(str(Path(temp_file.name)))
        temp_file.close()
        path_out = Path(temp_file.name)
        progress_message("Download processed file...")
        return DownloadResult(path_out.read_bytes(), "filtered_elements.ifc")

    @GeometryView("3D model of filtered elements", duration_guess=12)
    def ifc_view(self, params: Munch, **kwargs):
        """view the 3D model of filtered elements from uploaded .ifc file"""
        if not params.element_filter:
            # if no elements were selected to filter, assume the entire model to be rendered
            params.element_filter = get_element_options(params)
        trimesh_model = self._load_ifc_file_into_model(params)
        geometry = File()
        with geometry.open_binary() as w:
            w.write(trimesh.exchange.gltf.export_glb(trimesh_model))

        return GeometryResult(geometry)

    @WebView("What's next?", duration_guess=1)
    def whats_next(self, **kwargs):
        """Initiates the process of rendering the "What's next?" tab."""
        html_path = Path(__file__).parent / "final_step.html"
        with html_path.open() as f:
            html_string = f.read()
        return WebResult(html=html_string)

    @staticmethod
    def _load_ifc_file_into_model(params: Munch) -> Any:
        """Load ifc file into `trimesh.Scene` object.

        In the process, it also filters all the elements that were selected.
        """
        progress_message("Loading .ifc Model...")
        ifc_upload = _use_correct_file(params)
        path = ifc_upload.copy().source
        model = ifcopenshell.open(path)
        settings = ifcopenshell.geom.settings()
        settings.set(settings.USE_WORLD_COORDS, True)
        scene = trimesh.Scene()
        # initialize the variables responsible for progress message delays
        delta_time = PROGRESS_MESSAGE_DELAY + 1
        start = time.time()
        for ifc_entity in model.by_type("IfcElement"):
            if delta_time > PROGRESS_MESSAGE_DELAY:
                # the logic of progress message delays is implemented to avoid cases where the progress messages
                # flood the progress message queue
                start = time.time()
                progress_message(f"Meshing element: {ifc_entity.get_info()['type']}...")
            if ifc_entity.Representation and ifc_entity.get_info()["type"] in params.element_filter:
                shape = ifcopenshell.geom.create_shape(settings, ifc_entity)
                ios_vertices = shape.geometry.verts
                ios_faces = shape.geometry.faces

                vertices = [
                    [ios_vertices[i], ios_vertices[i + 1], ios_vertices[i + 2]] for i in range(0, len(ios_vertices), 3)
                ]
                faces = [[ios_faces[i], ios_faces[i + 1], ios_faces[i + 2]] for i in range(0, len(ios_faces), 3)]
                color = get_random_color(ifc_entity.get_info()["type"])
                mesh = trimesh.Trimesh(vertices=vertices, faces=faces, face_colors=color)

                scene.add_geometry(mesh)
            delta_time = time.time() - start
        return scene
