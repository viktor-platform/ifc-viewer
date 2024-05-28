import time
from collections import defaultdict
from io import BytesIO
from pathlib import Path
from pprint import pprint
from tempfile import NamedTemporaryFile
from typing import Any, List
import ifcopenshell
import ifcopenshell.geom
from munch import Munch
from viktor import File, ViktorController
from viktor.views import IFCView, IFCResult, DataView, DataResult, DataGroup, DataItem
from viktor.parametrization import (
    BooleanField,
    DownloadButton,
    FileField,
    MultiSelectField,
    Text,
    IsFalse,
    Lookup,
    ViktorParametrization,
    GeometryMultiSelectField, TextField
)
from viktor.result import DownloadResult
from viktor.core import progress_message
from viktor.errors import UserError, InputViolation

from ifcopenshell import file
from ifcopenshell.util.element import get_psets

PROGRESS_MESSAGE_DELAY = 3  # seconds


def _use_correct_file(params: Munch) -> File:
    if params.ifc_upload:
        return params.ifc_upload.file
    return File.from_path(Path(__file__).parent / "AC20-Institute-Var-2.ifc")


def _load_ifc_file(params: Munch) -> file:
    """Load ifc file into ifc model object."""
    ifc_upload = _use_correct_file(params)
    path = ifc_upload.copy().source
    model = ifcopenshell.open(path)
    return model


class Parametrization(ViktorParametrization):
    """Viktor parametrization."""
    text1 = Text(
        """
# Welcome to the IFC-viewer!💻
This app can import, view, analyze and download the elements of an IFC file.🏡
        """
    )
    text2 = Text(
        """
## 📂 File upload
Make sure that your file contains IfcElements with a geometry representation. If you do not provide your own file, 
the app will use a default IFC file.
        """
    )
    ifc_upload = FileField("Upload model", file_types=[".ifc"], flex=100, max_size=45_000_000,
                           description="If you leave this empty, the app will use a default file.")
    text3 = Text(
        """
## ✔️ Element filtering
Select which elements to analyze. 
Only elements existing in the IFC file can be selected. 
        """
    )
    selected_elements = GeometryMultiSelectField("Select elements")
    relevant_pset = TextField("PSET to analyze", flex=66, default="BaseQuantities", description="Select which PSET in your IFC file you want to analyze.")
    text4 = Text(
        """
## 💾 Download
Only selected elements will be downloaded.
        """
    )
    download = DownloadButton("Download", method="download_file", longpoll=True)
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
        return DownloadResult(ifc, 'name_of_file.ifc')

    @staticmethod
    def get_filtered_ifc_file(params: Munch, **kwargs) -> File:
        selected_elements = {int(element) for element in params.selected_elements}
        progress_message("Load IFC file...")
        model = _load_ifc_file(params)
        # initialize the variables responsible for progress message delays
        delta_time = PROGRESS_MESSAGE_DELAY + 1
        start = time.time()
        # remove all other parts from the ifc file which are not viewed
        for element in model.by_type("IfcElement"):
            if element.id not in selected_elements:
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
            if delta_time > PROGRESS_MESSAGE_DELAY:
                # the logic of progress message delays is implemented
                # to avoid cases where the progress messages
                # flood the progress message queue
                start = time.time()
                progress_message(f"Removing element: {element.get_info()['type']}")
            model.remove(element)
            delta_time = time.time() - start

        # part where we save the model as seen in the viewer
        progress_message("Exporting file...")
        file_ = File()
        model.write(file_.source)
        return file_

    @IFCView("IFC view", duration_guess=10)
    def get_ifc_view(self, params, **kwargs):
        ifc = _use_correct_file(params)
        return IFCResult(ifc)

    @DataView("Analysis on Selection", duration_guess=1)
    def get_analysis_view(self, params, **kwargs):
        if not params.selected_elements:
            raise UserError("No elements selected", input_violations=[
                InputViolation("This field cannot be empty!", fields=['selected_elements'])
            ])
        model = _load_ifc_file(params)
        try:
            _objects = [model.by_id(int(id_)) for id_ in params.selected_elements]
        except RuntimeError:
            raise UserError(
                "Selected elements not found in current IFC file. Please re-select the elements.",
                input_violations=[InputViolation("Selection mismatch with IFC file.", fields=['selected_elements'])]
            )

        objects_by_type = defaultdict(list)
        for obj in _objects:
            objects_by_type[obj.get_info()["type"]].append(obj)

        top_level_items = [DataItem("Number of objects selected", len(_objects), explanation_label="filtered by type")]
        for ifc_type, object_list in objects_by_type.items():
            mid_level_items = []
            for obj_ in object_list:
                low_level_items = [DataItem(key, val) for key, val in get_psets(obj_).get(params.relevant_pset, {}).items()]
                if low_level_items:
                    mid_level_items.append(DataItem(obj_.Name, "  ", subgroup=DataGroup(*low_level_items)))
                else:
                    mid_level_items.append(DataItem(obj_.Name, "(No BaseQuantities in psets)"))
            top_level_items.append(DataItem(ifc_type, len(object_list), subgroup=DataGroup(*mid_level_items)))
        return DataResult(DataGroup(*top_level_items))
