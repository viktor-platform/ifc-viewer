import time
from collections import defaultdict
from pathlib import Path

from ifcopenshell import open as openIFC
from ifcopenshell.util.element import get_psets

import viktor as vkt

PROGRESS_MESSAGE_DELAY = 3  # seconds


def _use_correct_file(params) -> vkt.File:
    """
    Returns either an uploaded file or a default one
    """
    if params.ifc_upload:
        return params.ifc_upload.file
    return vkt.File.from_path(Path(__file__).parent / "AC20-Institute-Var-2.ifc")


def _load_ifc_file(params):
    """Load ifc file into ifc model object."""
    ifc_upload = _use_correct_file(params)
    path = ifc_upload.copy().source
    model = openIFC(path)
    return model


def get_filtered_ifc_file(params, **kwargs) -> vkt.File:
    """
    Filter an IFC file based on selected elements and return the filtered file. This method Loads
    the IFC file. Then,  it filters out elements that are not in the `selected_elements` set, while it
    provides progress messages during the filtering process, avoiding any flooding of the message queue.
    In doing so, it removes all elements of type `IfcElement`, `IfcSpace` and IfcSite` that are not selected.
    Finally, it returns the filtered IFC as a VIKTOR file.
    """
    selected_elements = {int(element) for element in params.selected_elements}
    vkt.progress_message("Load IFC file...")
    model = _load_ifc_file(params)

    # initialize the variables responsible for progress message delays
    delta_time = PROGRESS_MESSAGE_DELAY + 1
    start = time.time()

    # remove all other parts from the ifc file which are not viewed
    for element in model.by_type("IfcElement"):
        if element.id() not in selected_elements:
            if delta_time > PROGRESS_MESSAGE_DELAY:
                # the logic of progress message delays is implemented
                # to avoid cases where the progress messages
                # flood the progress message queue
                start = time.time()
                vkt.progress_message(f"Removing element: {element.get_info()['type']}")
            model.remove(element)
        delta_time = time.time() - start
    
    # remove other types
    for t in ("IfcSpace", "IfcSite"):
        for element in model.by_type(t):
            if delta_time > PROGRESS_MESSAGE_DELAY:
                # the logic of progress message delays is implemented
                # to avoid cases where the progress messages
                # flood the progress message queue
                start = time.time()
                vkt.progress_message(f"Removing element: {element.get_info()['type']}")
            model.remove(element)
            delta_time = time.time() - start

    # part where we save the model as seen in the viewer
    vkt.progress_message("Exporting file...")
    file = vkt.File()
    model.write(file.source)
    return file


class Parametrization(vkt.ViktorParametrization):
    text1 = vkt.Text(
        """
# Welcome to the IFC-viewer!💻
In this app you can import, view, analyze and download the elements of an IFC file.🏡
        """
    )
    text2 = vkt.Text(
        """
## 📂 File upload
Make sure that your file contains IfcElements with a geometry representation. **If you do not provide your own file, 
the app will use a default IFC file.**
        """
    )
    ifc_upload = vkt.FileField(
        "Upload model",
        file_types=[".ifc"],
        flex=100,
        max_size=45_000_000,
        description="If you leave this empty, the app will use a default file.",
    )
    text3 = vkt.Text(
        """
## ✔️ Element filtering
Select which elements to analyze. 
Only elements existing in the IFC file can be selected. 
        """
    )
    selected_elements = vkt.GeometryMultiSelectField("Select elements")
    relevant_pset = vkt.TextField(
        "PSET to analyze",
        flex=66,
        default="BaseQuantities",
        description="Select which PSET in your IFC file you want to analyze.",
    )
    text4 = vkt.Text(
        """
## 💾 Download
Only selected elements will be downloaded.
        """
    )
    download = vkt.DownloadButton("Download", method="download_file", longpoll=True)


class Controller(vkt.ViktorController):
    label = "My Entity Type"
    parametrization = Parametrization(width=30)

    def download_file(self, params, **kwargs):
        ifc = get_filtered_ifc_file(params)
        return vkt.DownloadResult(ifc, "name_of_file.ifc")

    @vkt.IFCView("IFC view", duration_guess=10)
    def get_ifc_view(self, params, **kwargs):
        """
        View the current active IFC file; either uploaded by the user or default.
        """
        if params.selected_elements:
            ifc = get_filtered_ifc_file(params)
        else:
            ifc = _use_correct_file(params)
        return vkt.IFCResult(ifc)

    @vkt.DataView("Analysis on Selection", duration_guess=1)
    def get_analysis_view(self, params, **kwargs):
        """
        Generate an analysis view of selected IFC elements. This method checks if any elements are selected,
        raising a UserError if none are selected. Then, loads the IFC file based on the given parameters and attempts
        to retrieve the selected elements from the IFC file, raising a UserError if they are not found. It proceeds to
        group the selected elements by their IFC type and constructs a VIKTOR DataGroup with the number of
        selected objects, their types, and relevant property sets.
        """
        if not params.selected_elements:
            raise vkt.UserError(
                "No elements selected",
                input_violations=[
                    vkt.InputViolation(
                        "This field cannot be empty!", fields=["selected_elements"]
                    )
                ],
            )
        model = _load_ifc_file(params)
        try:
            _objects = [model.by_id(int(id_)) for id_ in params.selected_elements]
        except RuntimeError:
            raise vkt.UserError(
                "Selected elements not found in current IFC file. Please re-select the elements.",
                input_violations=[
                    vkt.InputViolation(
                        "Selection mismatch with IFC file.",
                        fields=["selected_elements"],
                    )
                ],
            )

        objects_by_type = defaultdict(list)
        for obj in _objects:
            objects_by_type[obj.get_info()["type"]].append(obj)

        top_level_items = [
            vkt.DataItem(
                "Number of objects selected",
                len(_objects),
                explanation_label="filtered by type",
            )
        ]
        for ifc_type, object_list in objects_by_type.items():
            mid_level_items = []
            for obj_ in object_list:
                low_level_items = [
                    vkt.DataItem(key, val)
                    for key, val in get_psets(obj_)
                    .get(params.relevant_pset, {})
                    .items()
                ]
                if low_level_items:
                    mid_level_items.append(
                        vkt.DataItem(obj_.Name, "  ", subgroup=vkt.DataGroup(*low_level_items))
                    )
                else:
                    mid_level_items.append(
                        vkt.DataItem(obj_.Name, "(No BaseQuantities in psets)")
                    )
            top_level_items.append(
                vkt.DataItem(
                    ifc_type, len(object_list), subgroup=vkt.DataGroup(*mid_level_items)
                )
            )
        return vkt.DataResult(vkt.DataGroup(*top_level_items))
