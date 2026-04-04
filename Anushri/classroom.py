from fastmcp import FastMCP
import gmail_service
from dotenv import load_dotenv

load_dotenv()

mcp=FastMCP("Google_Classroom")

@mcp.tool()
async def list_courses():
    """
    List all courses of Google Classroom.
    Use this first to find the 'id' of a specific course.
    """
    return await gmail_service.list_courses()

@mcp.tool()
async def get_announcements(course_id: str):
    """
    List all the latest posts and updates for a specific course using its course_id.
    """
    return await gmail_service.get_announcements(course_id)

@mcp.tool()
async def list_assignments(course_id: str): 
    """
    List all the coursework assignments for a specific course_id.
    """
    return await gmail_service.list_assignments(course_id)

@mcp.tool()
async def get_course_materials(course_id:str):
    """
    List all the non-graded materials for a specific course_id.
    """
    return await gmail_service.get_course_materials(course_id)

@mcp.tool()
async def get_submissions(course_id: str, assignment_id:str): 
    """
    View student uploaded files for a specific assignment_id within a course_id.
    """
    return await gmail_service.get_submissions(course_id, assignment_id)

if __name__ == "__main__":
    mcp.run()

