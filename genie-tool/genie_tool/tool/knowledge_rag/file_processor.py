# -*- coding: utf-8 -*-
# =====================
#
#
# Author: your_name
# Date:   YYYY/MM/DD
# =====================
import os
import re
import asyncio
from typing import List, Dict, Any, Optional

from genie_tool.util.log_util import logger

class FileProcessor:
    """文件处理器，支持处理多种文件格式"""
    
    def __init__(self):
        self.supported_extensions = {
            '.txt': self._process_txt,
            '.pdf': self._process_pdf,
            '.docx': self._process_docx,
            '.doc': self._process_doc,
            '.xlsx': self._process_xlsx,
            '.xls': self._process_xls,
            '.pptx': self._process_pptx,
            '.ppt': self._process_ppt,
            '.md': self._process_md
        }
        # 记录已加载的库
        self._libraries_loaded = {
            'PyPDF2': False,
            'docx': False,
            'textract': False,
            'pandas': False,
            'xlrd': False,
            'openpyxl': False,
            'pptx': False,
            'markdown': False
        }
        # 最大文件大小限制（100MB）
        self._max_file_size = 100 * 1024 * 1024
    
    def _load_library(self, lib_name: str, import_name: str = None):
        """
        延迟加载库并返回导入的模块
        
        Args:
            lib_name: 库的pip包名
            import_name: 导入时的名称（如果与包名不同）
            
        Returns:
            导入的模块或None
        """
        if self._libraries_loaded.get(lib_name):
            return globals().get(import_name or lib_name)
        
        import_name = import_name or lib_name
        
        try:
            module = __import__(import_name)
            globals()[import_name] = module
            self._libraries_loaded[lib_name] = True
            logger.info(f"Successfully loaded library: {lib_name}")
            return module
        except ImportError:
            logger.warning(f"Library {lib_name} not installed, some file formats may not be supported")
            self._libraries_loaded[lib_name] = False
            return None
    
    async def process_file(self, file_path: str) -> Dict[str, Any]:
        """
        处理文件
        
        Args:
            file_path: 文件路径
            
        Returns:
            包含文件内容和元数据的字典
        """
        start_time = asyncio.get_event_loop().time()
        file_name = os.path.basename(file_path) if file_path else "unknown"
        
        try:
            # 验证文件路径
            if not file_path or not isinstance(file_path, str):
                logger.error(f"Invalid file path: {file_path}")
                return {
                    "error": "Invalid file path", 
                    "status": "failed", 
                    "file_path": file_path,
                    "file_name": file_name,
                    "processing_time_ms": 0
                }
            
            # 检查文件是否存在
            if not os.path.exists(file_path):
                logger.error(f"File not found: {file_path}")
                return {
                    "error": f"File not found: {file_path}", 
                    "status": "failed", 
                    "file_path": file_path,
                    "file_name": file_name,
                    "processing_time_ms": 0
                }
            
            # 检查是否为文件（不是目录）
            if not os.path.isfile(file_path):
                logger.error(f"Path is not a file: {file_path}")
                return {
                    "error": "Path is not a file", 
                    "status": "failed", 
                    "file_path": file_path,
                    "file_name": file_name,
                    "processing_time_ms": 0
                }
            
            # 检查文件大小
            file_size = os.path.getsize(file_path)
            if file_size > self._max_file_size:
                logger.error(f"File too large: {file_path} ({file_size/1024/1024:.2f}MB, max: {self._max_file_size/1024/1024:.0f}MB)")
                return {
                    "error": f"File too large (max {self._max_file_size/1024/1024:.0f}MB)", 
                    "status": "failed", 
                    "file_path": file_path,
                    "file_name": file_name,
                    "file_size_bytes": file_size,
                    "processing_time_ms": 0
                }
            
            file_ext = os.path.splitext(file_path)[1].lower()
            
            if file_ext not in self.supported_extensions:
                logger.warning(f"Unsupported file format: {file_ext} for file: {file_path}")
                return {
                    "error": f"Unsupported file format: {file_ext}", 
                    "status": "failed", 
                    "file_path": file_path,
                    "file_name": file_name,
                    "processing_time_ms": 0
                }
            
            logger.info(f"Processing file: {file_path} (size: {file_size/1024:.2f}KB, type: {file_ext})")
            
            # 调用对应的处理函数
            content = await self.supported_extensions[file_ext](file_path)
            
            processing_time = asyncio.get_event_loop().time() - start_time
            
            if not content:
                logger.warning(f"File content is empty: {file_path}")
                return {
                    "file_path": file_path,
                    "file_name": file_name,
                    "content": "",
                    "content_length": 0,
                    "status": "success",
                    "warning": "File content is empty",
                    "processing_time_ms": int(processing_time * 1000),
                    "file_size_bytes": file_size
                }
            
            # 预处理内容
            content = self.preprocess_content(content)
            
            logger.info(f"Successfully processed file: {file_path} (content length: {len(content)}, time: {processing_time:.2f}s)")
            
            return {
                "file_path": file_path,
                "file_name": file_name,
                "content": content,
                "content_length": len(content),
                "status": "success",
                "processing_time_ms": int(processing_time * 1000),
                "file_size_bytes": file_size
            }
            
        except PermissionError:
            processing_time = asyncio.get_event_loop().time() - start_time
            logger.error(f"Permission denied when accessing file: {file_path}")
            return {
                "file_path": file_path,
                "file_name": file_name,
                "error": "Permission denied",
                "status": "failed",
                "processing_time_ms": int(processing_time * 1000)
            }
        except OSError as e:
            processing_time = asyncio.get_event_loop().time() - start_time
            logger.error(f"OS error processing file {file_path}: {str(e)}", exc_info=True)
            return {
                "file_path": file_path,
                "file_name": file_name,
                "error": f"OS error: {str(e)}",
                "status": "failed",
                "processing_time_ms": int(processing_time * 1000)
            }
        except Exception as e:
            processing_time = asyncio.get_event_loop().time() - start_time
            logger.error(f"Unexpected error processing file {file_path}: {str(e)}", exc_info=True)
            return {
                "file_path": file_path,
                "file_name": file_name,
                "error": f"Unexpected error: {str(e)}",
                "status": "failed",
                "processing_time_ms": int(processing_time * 1000)
            }
    
    async def _process_txt(self, file_path: str) -> str:
        """处理txt文件"""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            return content.strip()
        except UnicodeDecodeError:
            # 尝试其他编码
            try:
                with open(file_path, 'r', encoding='gbk', errors='ignore') as f:
                    content = f.read()
                return content.strip()
            except Exception as e:
                logger.error(f"Error processing txt file {file_path}: {str(e)}")
                return ""
        except Exception as e:
            logger.error(f"Error processing txt file {file_path}: {str(e)}")
            return ""
    
    async def _process_pdf(self, file_path: str) -> str:
        """处理pdf文件"""
        PyPDF2 = self._load_library('PyPDF2')
        if not PyPDF2:
            logger.error(f"PyPDF2 not installed, cannot process PDF: {file_path}")
            return ""
        
        try:
            content = ""
            with open(file_path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                num_pages = len(reader.pages)
                logger.debug(f"PDF file has {num_pages} pages")
                
                for page_num in range(num_pages):
                    page = reader.pages[page_num]
                    page_text = page.extract_text()
                    if page_text:
                        content += page_text + "\n\n"
            
            return content.strip()
        except Exception as e:
            logger.error(f"Error processing pdf file {file_path}: {str(e)}", exc_info=True)
            return ""
    
    async def _process_docx(self, file_path: str) -> str:
        """处理docx文件"""
        docx_module = self._load_library('python-docx', 'docx')
        if not docx_module:
            logger.error(f"python-docx not installed, cannot process DOCX: {file_path}")
            return ""
        
        try:
            doc = docx_module.Document(file_path)
            content = ""
            
            # 提取段落文本
            for paragraph in doc.paragraphs:
                if paragraph.text.strip():
                    content += paragraph.text + "\n"
            
            # 提取表格内容
            for table in doc.tables:
                for row in table.rows:
                    row_text = "\t".join(cell.text for cell in row.cells)
                    content += row_text + "\n"
            
            return content.strip()
        except Exception as e:
            logger.error(f"Error processing docx file {file_path}: {str(e)}", exc_info=True)
            return ""
    
    async def _process_doc(self, file_path: str) -> str:
        """处理doc文件"""
        textract = self._load_library('textract')
        if not textract:
            logger.error(f"textract not installed, cannot process DOC: {file_path}")
            return ""
        
        try:
            content = textract.process(file_path).decode('utf-8', errors='ignore')
            return content.strip()
        except Exception as e:
            logger.error(f"Error processing doc file {file_path}: {str(e)}", exc_info=True)
            return ""
    
    async def _process_xlsx(self, file_path: str) -> str:
        """处理xlsx文件"""
        pandas = self._load_library('pandas')
        if not pandas:
            logger.error(f"pandas not installed, cannot process XLSX: {file_path}")
            return ""
        
        # 尝试加载openpyxl作为xlsx引擎
        openpyxl = self._load_library('openpyxl')
        if not openpyxl:
            logger.warning(f"openpyxl not installed, using default engine for XLSX: {file_path}")
        
        try:
            # 读取所有sheet
            engine = 'openpyxl' if openpyxl else None
            xls = pandas.ExcelFile(file_path, engine=engine)
            content = ""
            
            for sheet_name in xls.sheet_names:
                content += f"=== Sheet: {sheet_name} ===\n"
                df = pandas.read_excel(file_path, sheet_name=sheet_name, engine=engine)
                content += df.to_string(index=False, na_rep='') + "\n\n"
            
            return content.strip()
        except ImportError as e:
            logger.error(f"Missing dependency for XLSX processing: {str(e)}")
            return ""
        except Exception as e:
            logger.error(f"Error processing xlsx file {file_path}: {str(e)}", exc_info=True)
            return ""
    
    async def _process_xls(self, file_path: str) -> str:
        """处理xls文件"""
        pandas = self._load_library('pandas')
        xlrd = self._load_library('xlrd')
        
        if not pandas or not xlrd:
            logger.error(f"pandas or xlrd not installed, cannot process XLS: {file_path}")
            return ""
        
        try:
            xls = pandas.ExcelFile(file_path, engine='xlrd')
            content = ""
            
            for sheet_name in xls.sheet_names:
                content += f"=== Sheet: {sheet_name} ===\n"
                df = pandas.read_excel(file_path, sheet_name=sheet_name, engine='xlrd')
                content += df.to_string(index=False) + "\n\n"
            
            return content.strip()
        except Exception as e:
            logger.error(f"Error processing xls file {file_path}: {str(e)}", exc_info=True)
            return ""
    
    async def _process_pptx(self, file_path: str) -> str:
        """处理pptx文件"""
        pptx = self._load_library('python-pptx', 'pptx')
        if not pptx:
            logger.error(f"python-pptx not installed, cannot process PPTX: {file_path}")
            return ""
        
        try:
            prs = pptx.Presentation(file_path)
            content = ""
            
            for slide_num, slide in enumerate(prs.slides, 1):
                content += f"=== Slide {slide_num} ===\n"
                
                for shape in slide.shapes:
                    if hasattr(shape, 'text') and shape.text.strip():
                        content += shape.text + "\n"
                
                content += "\n"
            
            return content.strip()
        except Exception as e:
            logger.error(f"Error processing pptx file {file_path}: {str(e)}", exc_info=True)
            return ""
    
    async def _process_ppt(self, file_path: str) -> str:
        """处理ppt文件"""
        textract = self._load_library('textract')
        if not textract:
            logger.error(f"textract not installed, cannot process PPT: {file_path}")
            return ""
        
        try:
            content = textract.process(file_path).decode('utf-8', errors='ignore')
            return content.strip()
        except Exception as e:
            logger.error(f"Error processing ppt file {file_path}: {str(e)}", exc_info=True)
            return ""
    
    async def _process_md(self, file_path: str) -> str:
        """处理markdown文件"""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # 优先尝试使用markdown库解析
            markdown_lib = self._load_library('markdown')
            if markdown_lib:
                try:
                    # 转换为HTML，然后提取纯文本
                    html_content = markdown_lib.markdown(content, extensions=['extra', 'tables', 'fenced_code'])
                    # 移除HTML标签，保留文本结构
                    text_content = re.sub(r'<[^>]*>', '\n', html_content)
                except Exception as e:
                    logger.warning(f"Failed to parse markdown with library, using plain text: {str(e)}")
                    text_content = content
            else:
                text_content = content
            
            # 清理多余空白和特殊字符
            # 保留合理的段落结构
            lines = text_content.split('\n')
            cleaned_lines = []
            
            for line in lines:
                # 清理行内多余空格
                cleaned_line = ' '.join(line.split())
                # 移除markdown特殊标记但保留内容
                cleaned_line = re.sub(r'^#+\s*', '', cleaned_line)  # 移除标题标记
                cleaned_line = re.sub(r'^\*\*\s*', '', cleaned_line)  # 移除粗体列表
                cleaned_line = re.sub(r'^\*\s*', '', cleaned_line)   # 移除普通列表
                cleaned_line = re.sub(r'^>\s*', '', cleaned_line)   # 移除引用
                cleaned_line = re.sub(r'`{1,3}', '', cleaned_line)   # 移除代码标记
                
                if cleaned_line:
                    cleaned_lines.append(cleaned_line)
            
            # 重新组合，保留段落分隔
            result = '\n\n'.join(cleaned_lines)
            
            return result.strip()
            
        except Exception as e:
            logger.error(f"Error processing md file {file_path}: {str(e)}", exc_info=True)
            return ""
    
    async def process_files_batch(self, file_paths: List[str]) -> List[Dict[str, Any]]:
        """
        批量处理文件
        
        Args:
            file_paths: 文件路径列表
            
        Returns:
            处理结果列表
        """
        if not file_paths or not isinstance(file_paths, list):
            logger.warning("Empty or invalid file paths list")
            return []
        
        logger.info(f"Starting batch processing of {len(file_paths)} files")
        
        # 过滤无效路径
        valid_paths = [fp for fp in file_paths if fp and isinstance(fp, str) and os.path.exists(fp)]
        invalid_count = len(file_paths) - len(valid_paths)
        
        if invalid_count > 0:
            logger.warning(f"Skipped {invalid_count} invalid or non-existent files")
        
        # 并发处理文件
        tasks = [self.process_file(file_path) for file_path in valid_paths]
        results = await asyncio.gather(*tasks)
        
        # 统计结果
        success_count = sum(1 for r in results if r.get("status") == "success")
        failed_count = len(results) - success_count
        
        logger.info(f"Batch processing completed: {success_count} success, {failed_count} failed")
        
        return results
    
    def preprocess_content(self, content: str, max_length: int = 10000) -> str:
        """
        预处理文本内容
        
        Args:
            content: 原始文本内容
            max_length: 最大长度限制
            
        Returns:
            预处理后的文本内容
        """
        if not content:
            return ""
        
        # 去除多余空白字符（保留段落结构）
        lines = content.split('\n')
        cleaned_lines = []
        
        for line in lines:
            # 清理每行的多余空格
            cleaned_line = ' '.join(line.split())
            if cleaned_line:
                cleaned_lines.append(cleaned_line)
        
        # 重新组合
        content = '\n'.join(cleaned_lines)
        
        # 限制长度
        if len(content) > max_length:
            logger.debug(f"Content truncated from {len(content)} to {max_length} characters")
            content = content[:max_length] + "..."
        
        return content
    
    def get_supported_formats(self) -> List[str]:
        """
        获取支持的文件格式列表
        
        Returns:
            支持的文件扩展名列表
        """
        return list(self.supported_extensions.keys())
    
    def is_format_supported(self, file_path: str) -> bool:
        """
        检查文件格式是否支持
        
        Args:
            file_path: 文件路径
            
        Returns:
            是否支持该格式
        """
        if not file_path:
            return False
        
        file_ext = os.path.splitext(file_path)[1].lower()
        return file_ext in self.supported_extensions