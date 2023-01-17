# ifc-viewer
Sample app demonstrating how to import and view IFC files.
The IFC filetype (.ifc) is an international standard to import and export building objects and their properties. Most BIM-software packages allow you to import and export IFC files. With this application we want to show how to handle IFC files in a Viktor application.

# File upload
The file upload size is now capped at 20mb. This can be adjusted by the developer. Make sure that your file contains IfcElements with a geometry representation. The app is tested with IFC 4 files. For example files, check out:
https://www.ifcwiki.org/index.php?title=KIT_IFC_Examples

# Element filtering
Select which elements to preview. Only elements existing in the IFC file can be selected. Geometry of selected elements will be shown in the 3D viewer. 

# View
Click update to refresh the view. Click the elipsis (...) to export to other file formats, or download an image.

![Screenshot 2023-01-17 124540](https://user-images.githubusercontent.com/93203883/212890966-abe00283-98d8-42ba-83b9-46826b15a931.png)
