from enum import Enum
from typing import List, Dict, Any, Union, Optional
import os
from openagent import compiler
from openagent.tools.basetool import BaseTool
import logging
import yaml
import yaml
import importlib
import argparse

def import_class(class_path):
    module_name, class_name = class_path.rsplit(".", 1)
    module = importlib.import_module(module_name)
    return getattr(module, class_name)

class AgentState(Enum):
    """Enum to represent different states of the Agent"""

    IDLE = 0
    BUSY = 1
    USED_AS_TOOL = 2
    ERROR = 3


class BaseAgent:
    def __init__(self,
                knowledgebase: Optional[Any] = None,
                tools: Optional[Any] = None,
                llm: Optional[Any] = None,
                prompt_template: str = None,
                input_variables: Dict = {},
                agent_id: str = "default",
                memory: Any = None,
                caching: bool = False,
                output_key: str = None,
                return_complete: bool = False
                ):
        
        self.agent_id = agent_id
        self.knowledgebase = knowledgebase
        self.tools = tools
        self.llm = llm
        self.prompt_template = prompt_template
        self.input_variables = input_variables
        self.memory = memory
        self.state = AgentState.IDLE
        self.caching = caching
        self.return_complete = return_complete
        self.llm = llm if llm is not None else self.llm_instance()
        self.output_key = output_key

        self.compiler = compiler(llm = self.llm, template = self.prompt_template, caching=caching)

        if self.return_complete and self.output_key is not None:
            logging.warning("return_complete mode is enabled. Output key will be ignored.")

        if self.knowledgebase is not None and not self.input_variables.get('knowledge_variable'):
            raise ValueError ("knowledge_variable should be present in input_variables while using knowledge")


    @property
    def agent_type(self):
        pass

    @property
    def get_knowledge_variable(self):
        """Get knowledge variable name from input variables"""
        pass
    
    @property
    def default_llm_model(self):
        pass
        
    def add_tool(self, tool: BaseTool) -> None:
        """Add a tool to the agent's tool list."""
        self.tools.append(tool)

    def remove_tool(self, tool: BaseTool) -> None:
        """Remove a tool from the agent's tool list."""
        if tool in self.tools:
            self.tools.remove(tool)

    def llm_instance(self) -> compiler.llms.OpenAI:
        """Create an instance of the language model."""
        pass
    
    def get_output_key(self, prompt):
        vars = prompt.variables()
        vars = list(vars.keys())
        return vars[-1]

    def get_knowledge(self, query) -> List[str]:
        docs = self.knowledgebase.retrieve_data(query)
        final_doc = ""
        for doc in docs:
            final_doc += doc
        return final_doc

    def run(self, **kwargs) -> Union[str, Dict[str, Any]]:
        """Run the agent to generate a response to the user query."""
    
        _knowledge_variable = self.get_knowledge_variable

        if _knowledge_variable:
            if kwargs.get(_knowledge_variable):
                query = kwargs.get(_knowledge_variable)
                retrieved_knowledge = self.get_knowledge(query)
                output = self.compiler(RETRIEVED_KNOWLEDGE = retrieved_knowledge, **kwargs, silent = True)
            else:
                raise ValueError("knowledge_variable not found in input kwargs")
        else:
            output = self.compiler(**kwargs, silent = True)

        if self.return_complete:
            return output
        
        _output_key = self.output_key if self.output_key is not None else self.get_output_key(output)

        if output.variables().get(_output_key):
            return output[_output_key]
        else:
            logging.warning("Output key not found in output, so full output returned")
            return output
        

    def cli(self):
        """Start a CLI for interacting with the agent."""
        print("Welcome to the agent CLI!")

        _vars = []
        for _, v in self.input_variables.items():
            if isinstance(v, str):
                _vars.append(v)
            if isinstance(v, List):
                _vars.extend(v)
        
        parser = argparse.ArgumentParser(description="CLI for interacting with the Agent instance.")

        for var in _vars:
            parser.add_argument(f"--{var}", help=f"Pass {var} as an input variable")

        args = parser.parse_args()
        
        print(self.run(**vars(args)))


    def cli_inputs(self):
        """Start a CLI for interacting with the agent."""
        print("Welcome to the agent CLI!")

        _vars = []
        kwargs = {}
        for _, v in self.input_variables.items():
            if isinstance(v, str):
                _vars.append(v)
            if isinstance(v, List):
                _vars.extend(v)

        for var in _vars:
            kwargs[var] = input(f"{var}: ".capitalize())
        
        print(self.run(**kwargs))


    def export_agent_config(self, config_path):
        config = {
            'llm': {
                'type': f"{self.llm.__class__.__name__}",
                'model': self.llm.model_name
            },
            'knowledgebase': None if self.knowledgebase is None else {
                'type': self.knowledgebase.__class__.__module__ + '.' +
                        self.knowledgebase.__class__.__name__,
                'data_references': self.knowledgebase.references,
                'data_transformer': {
                    'type': self.knowledgebase.data_transformer.__class__.__module__ + '.' +
                            self.knowledgebase.data_transformer.__class__.__name__,
                    'chunk_overlap': self.knowledgebase.data_transformer._chunk_overlap,
                    'chunk_size': self.knowledgebase.data_transformer._chunk_size
                },
                'vector_store': {
                    'type': self.knowledgebase.vector_store.__class__.__module__ + '.' +
                            self.knowledgebase.vector_store.__class__.__name__,
                    'embedding_function': self.knowledgebase.vector_store._embedding_function
                }
            },
            'memory' : None if self.memory is None else {
                'type' : self.memory.__class__.__module__ + '.' +
                        self.memory.__class__.__name__,
            },
            'prompt_template': self.prompt_template,
            'input_variables': self.input_variables,
            'output_key': self.output_key,
            # 'tools': None if self.tools is None else self.tools
        }
        with open(config_path, 'w') as f:
            f.write(config)


    @classmethod
    def load_from_config(cls, config_file):
        with open(config_file, 'r') as f:
            config = f.read()

        # Assume these classes are defined elsewhere and can be imported
        llm_module_name, llm_class_name = config['llm']['type'].rsplit('.', 1)
        llm_module = importlib.import_module(llm_module_name)
        llm_class = getattr(llm_module, llm_class_name)
        llm = llm_class(model=config['llm']['model'])

        knowledgebase = None
        if config['knowledgebase'] is not None:
            knowledgebase_module_name, knowledgebase_class_name = config['agent']['type'].rsplit('.', 1)
            knowledgebase_module = importlib.import_module(knowledgebase_module_name)
            knowledgebase_class = getattr(knowledgebase_module, knowledgebase_class_name)
            knowledgebase = knowledgebase_class(
                data_references=config['knowledgebase']['data_references'],
                data_transformer=config['knowledgebase']['data_transformer'],
                vector_store=config['knowledgebase']['vector_store']
            )

        memory = None
        if config['memory'] is not None:
            # Instantiate the memory here in a similar manner
            memory_module_name, memory_class_name = config['memory']['type'].rsplit('.', 1)
            memory_module = importlib.import_module(memory_module_name)
            memory_class = getattr(memory_module, memory_class_name)
            memory = memory_class()

        agent = cls(
            llm=llm,
            knowledgebase=knowledgebase,
            memory=memory,
            prompt_template=config['agent']['prompt_template'],
            input_variables=config['agent']['input_variables'],
            output_key=config['agent']['output_key'],
        )

        return agent



