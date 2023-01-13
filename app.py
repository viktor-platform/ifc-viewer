from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import List

import ifcopenshell
import ifcopenshell.geom as geom
from shapely import affinity, Point
from viktor import ViktorController, File, Color, geometry
from viktor.geometry import Triangle, TriangleAssembly, Material
from viktor.parametrization import ViktorParametrization, FileField, MultiSelectField
from viktor.views import GeometryView, GeometryResult


ELEMENT_OPTIONS = {
    'IfcWall': Color(255, 204, 153),
    'IfcRoof': Color(255, 153, 153),
    'IfcSlab': Color(128, 128, 128)
}


class Parametrization(ViktorParametrization):
    ifc_upload = FileField("Upload model", file_types=[".ifc"], max_size=10_000_000)
    element_filter = MultiSelectField(
        "Filter elements", options=list(ELEMENT_OPTIONS.keys())
    )


class Controller(ViktorController):
    label = 'My Entity Type'
    parametrization = Parametrization

    @staticmethod
    @GeometryView("3D model", duration_guess=12)
    def ifc_view(params, **kwargs):
        """View 3D model of uploaded .ifc file."""

        # Load ifc upload into model
        ifc_upload: File = params.ifc_upload.file
        temp_file = NamedTemporaryFile(suffix='.sld', delete=False, mode='wb')
        temp_file.write(ifc_upload.getvalue_binary())
        temp_file.close()
        path = Path(temp_file.name)
        model = ifcopenshell.open(path)

        # Settings
        selected_elements = params.element_filter
        elements = []
        geometry_groups = []
        settings = ifcopenshell.geom.settings()

        # Get geometry from selected elements
        for element_type in selected_elements:
            material = Material(
                name=element_type,
                color=ELEMENT_OPTIONS[element_type]
            )
            elements.extend(model.by_type(element_type))
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
    verts = shape.geometry.verts

    # A 4x4 matrix representing the location and rotation of the element, in the form:
    # [ [ x_x, y_x, z_x, x   ]
    #   [ x_y, y_y, z_y, y   ]
    #   [ x_z, y_z, z_z, z   ]
    #   [ 0.0, 0.0, 0.0, 1.0 ] ]
    # The position is given by the last column: (x, y, z)
    # The rotation is described by the first three columns,
    # by explicitly specifying the local X, Y, Z axes.
    # The first column is a normalised vector of the local X axis: (x_x, x_y, x_z)
    # The second column is a normalised vector of the local Y axis: (y_x, y_y, y_z)
    # The third column is a normalised vector of the local Z axis: (z_x, z_y, z_z)
    # The axes follow a right-handed coordinate system.
    # Objects are never scaled, so the scale factor of the matrix is always 1.
    matrix = shape.transformation.matrix.data
    shapely_points = []
    for i in range(0, len(verts), 3):
        point = affinity.affine_transform(
            Point(
                verts[i],
                verts[i + 1],
                verts[i + 2]
            ),
            matrix,
        )
        shapely_points.append(point)

    grouped_verts = []
    for point in shapely_points:
        grouped_verts.append(geometry.Point(point.x, point.y, point.z))

    grouped_faces = [
        Triangle(
            grouped_verts[faces[i]],
            grouped_verts[faces[i + 1]],
            grouped_verts[faces[i + 2]]
        )
        for i in range(0, len(faces), 3)
    ]
    return grouped_faces
