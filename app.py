import time
import random
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, List
import trimesh
import multiprocessing
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
    SetParamsButton,
    HiddenField,
)
from viktor.result import DownloadResult, SetParametersResult
from viktor.views import GeometryResult, GeometryView, WebView, WebResult
from viktor.core import progress_message, Storage


PROGRESS_MESSAGE_DELAY = 3  # seconds


text_start = """    
    # Welcome to the ifc-viewer app!

    This is a sample app demonstrating how to import, view, seperate and download the 
    elements of an IFC files. 
    The IFC filetype (.ifc) is an international standard to import and 
    export building objects and their properties. 
    Most BIM-software packages allow you to import and export IFC files. 
    With this application we want to show that a VIKTOR application can handle and 
    transform your .ifc file. 
    The source code of this application can be found on 
    [github](https://github.com/viktor-platform/ifc-viewer).

    ## File upload
    Make sure that your file contains IfcElements with a geometry representation. 
    The app is tested with IFC 4 files. For reference, check out some 
    [example files](https://www.ifcwiki.org/index.php?title=KIT_IFC_Examples)."""


text_element_filter = """
## Element filtering
Select which elements to preview. 
Only elements existing in the IFC file can be selected. 
Geometry of selected elements will be shown in the 3D viewer. """

text_download = """
## Download
Only selected elements will be downloaded, this allows for easy removal 
of any of the elements that are not needed. This is a useful application 
for when a colleague may want to perform some analysis on structural elements 
only. """ 

def _use_correct_file(params: Munch):
    if params.get_sample_ifc_toggle is True:
        params.use_file = File.from_path(
            Path(__file__).parent / "KIT-Bridge.ifc"
        )
    else:
        params.use_file = params.ifc_upload.file
    return params.use_file

def show_elements(params, **kwargs):
    return params.data_file["elements"]

def show_sub_elements(params, **kwargs):
    return params.data_file["sub_elements"]

def get_lists(model):
    filter_elements = {}
    elements = model.by_type("IfcElement")
    
    for element in elements:
        type_element = element.get_info()["type"]
        sub_elements = model.by_type(type_element)

        for sub_element in sub_elements:
            name_element = sub_element.get_info()["Name"]
            if type_element not in filter_elements and sub_element.Representation:
                filter_elements[type_element] = [name_element]
            elif sub_element.Representation:
                filter_elements[type_element].append(name_element)
    
    # Create list of all sub elements
    list_sub_elements = []
    for sublist in list(filter_elements.values()):
        list_sub_elements.extend(filter(None, sublist))
    
    # Create list of all elements 
    list_elements = list(filter(None, filter_elements.keys()))

    return list_elements, list_sub_elements, filter_elements
    
        
            
    
    


def _load_ifc_file(params: Munch) -> Any:
    """Load ifc file into ifc model object."""
    ifc_upload = _use_correct_file(params)
    path = ifc_upload.copy().source
    model = ifcopenshell.open(path)
    return model

       
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
    data_file = HiddenField("data_file")
    text1 = Text(text_start)
        

    ifc_upload = FileField(
        "Upload model",
        file_types=[".ifc"],
        visible=IsFalse(Lookup("get_sample_ifc_toggle")),
        max_size=500_000_000,
    )

    button = SetParamsButton("Analyse model", method="analyse_file")


    get_sample_ifc_toggle = BooleanField(
        "Use sample IFC File",
        default=True,
        flex=30,
    )

    lb = LineBreak()
    text2 = Text(text_element_filter)
    element_filter = MultiSelectField(
        "Filter elements",
        options= show_elements,
    )
    lb2 = LineBreak()
    sub_element_filter = MultiSelectField(
        "Filter sub elements",
        options= show_sub_elements,
    )

    lb3 = LineBreak()
    text3 = Text(text_download)
    download = DownloadButton(
        "Download",
        method="download_file",
        longpoll=True,
    )

class Controller(ViktorController):
    """Viktor Controller."""

    label = "My Entity Type"
    parametrization = Parametrization
    viktor_enforce_field_constraints = True

    
    def analyse_file(self, params, **kwargs):

        progress_message("Load IFC file...")
        model = _load_ifc_file(params)
        
        progress_message("Get elements...")
        list_elements, list_sub_elements, filter_elements = get_lists(model)




        
        return SetParametersResult({"data_file":{"elements": list_elements,
                                                 "sub_elements":list_sub_elements,
                                                 "filter_elements": filter_elements}})


    @staticmethod
    def download_file(params: Munch, **kwargs):
        progress_message("Load IFC file...")
        model = _load_ifc_file(params)
        # initialize the variables responsible for progress message delays
        delta_time = PROGRESS_MESSAGE_DELAY + 1
        start = time.time()
        # remove all other parts from the ifc file which are not viewed
        for element in model.by_type("IfcElement"):
            element_name = element.get_info()["Name"]
            if element_name not in params.sub_element_filter:
                print("Wordt verwijdert")
                if delta_time > PROGRESS_MESSAGE_DELAY:
                    # the logic of progress message delays is implemented
                    # to avoid cases where the progress messages
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
            # if no elements were selected to filter, assume the
            # entire model to be rendered
            params.element_filter = params.data_file["elements"]
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

        filtered_elements = params.data_file["filter_elements"]
        print(filtered_elements)
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
            type_element = ifc_entity.get_info()["type"]
            name = ifc_entity.get_info()["Name"]
            id = ifc_entity.get_info()["id"]

            if delta_time > PROGRESS_MESSAGE_DELAY:
                # the logic of progress message delays is implemented to avoid
                # cases where the progress messages
                # flood the progress message queue
                start = time.time()
                progress_message(f"Meshing element: {type_element}, Name: {name}...")
            

            if name in list(params.sub_element_filter):
                
                shape = ifcopenshell.geom.create_shape(settings, ifc_entity)
                ios_vertices = shape.geometry.verts
                ios_faces = shape.geometry.faces

                

                vertices = [
                    [ios_vertices[i], ios_vertices[i + 1], ios_vertices[i + 2]]
                    for i in range(0, len(ios_vertices), 3)
                ]
                faces = [
                    [ios_faces[i], ios_faces[i + 1], ios_faces[i + 2]]
                    for i in range(0, len(ios_faces), 3)
                ]
                color = get_random_color(ifc_entity.get_info()["type"])
                mesh = trimesh.Trimesh(
                    vertices=vertices, faces=faces, face_colors=color
                )

                scene.add_geometry(mesh)
            delta_time = time.time() - start
        return scene
