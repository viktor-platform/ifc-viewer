import time
from io import BytesIO
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, List
import ifcopenshell
import ifcopenshell.geom
from munch import Munch
from viktor import  File, ViktorController
from viktor.views import IFCView,IFCResult
from viktor.parametrization import (
    BooleanField,
    DownloadButton,
    FileField,
    MultiSelectField,
    Text,
    IsFalse,
    Lookup,
    ViktorParametrization,
)
from viktor.result import DownloadResult
from viktor.core import progress_message


PROGRESS_MESSAGE_DELAY = 3  # seconds

def _use_correct_file(params: Munch) -> File:
    if params.get_sample_ifc_toggle is True:
        params.use_file = File.from_path(
            Path(__file__).parent / "rac_advanced_sample_project.ifc"
        )
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

class Parametrization(ViktorParametrization):
    """Viktor parametrization."""
    text1 = Text(
        """
# Welcome to the IFC-viewer!💻
This app can import, view, separate and download the 
elements of an IFC file. The app uses a default IFC file. Alternatively, you can use your own.🏡
        """
    )
    get_sample_ifc_toggle = BooleanField(
        "Default IFC File",
        default=True,
        flex=30,
    )
    text2 = Text(
        """
## 📂 File upload
Make sure that your file contains IfcElements with a geometry representation. 
        """
    )
    ifc_upload = FileField(
        "Upload model",
        file_types=[".ifc"],
        visible=IsFalse(Lookup("get_sample_ifc_toggle")),
        max_size=45_000_000,
    )
    text3 = Text(
        """
## ✔️ Element filtering
Select which elements to preview. 
Only elements existing in the IFC file can be selected. 
        """
    )
    element_filter = MultiSelectField(
        "Filter elements",
        options=get_element_options,
    )
    text4 = Text(
        """
## 💾 Download
Only selected elements will be downloaded.
        """
    )
    download = DownloadButton(
        "Download",
        method="download_file",
        longpoll=True,
    )
    text5 = Text(
        """
Start building cloud apps [now.](https://www.viktor.ai/start-building-apps)
Or check more apps created by others in our [Apps Gallery](https://www.viktor.ai/apps-gallery/category/all/discipline/all/integration/all/1)🚀 
        """
    )

class Controller(ViktorController):
    """Viktor Controller."""

    label = "My Entity Type"
    parametrization = Parametrization(width=30)
    viktor_enforce_field_constraints = True

    def download_file(self, params, **kwargs):
        ifc = self.get_filtered_ifc_file(params)
        return DownloadResult(BytesIO(ifc.getvalue_binary()), 'name_of_file.ifc')

    @staticmethod
    def get_filtered_ifc_file(params: Munch, **kwargs) -> File:
        progress_message("Load IFC file...")
        model = _load_ifc_file(params)
        # initialize the variables responsible for progress message delays
        delta_time = PROGRESS_MESSAGE_DELAY + 1
        start = time.time()
        # remove all other parts from the ifc file which are not viewed
        print(params.element_filter)
        for element in model.by_type("IfcElement"):
            if element.get_info()["type"] not in params.element_filter:
                # print(element.get_info()["type"] )
                if delta_time > PROGRESS_MESSAGE_DELAY:
                    # the logic of progress message delays is implemented
                    # to avoid cases where the progress messages
                    # flood the progress message queue
                    start = time.time()
                    progress_message(f"Removing element: {element.get_info()['type']}")
                model.remove(element)
            delta_time = time.time() - start

        for element in model.by_type("ifcspace"):

            # print(element.get_info()["type"] )
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
        action_view = File.from_data(path_out.read_bytes())
        return action_view


    @IFCView("IFC view", duration_guess=10)
    def get_ifc_view(self, params, **kwargs):
        if not params.element_filter:
            ifc = _use_correct_file(params)
        else:
            ifc = self.get_filtered_ifc_file(params)
        return IFCResult(ifc)
