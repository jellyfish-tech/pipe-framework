import re
import typing as t

import valideer as V
from frozendict import frozendict
from pipe.core.exceptions import StepExecutionException, StepValidationException
from rich.console import Console


class Step:
    """
    Base class providing basic functionality for all steps related classes

    There are three types of steps:

    Extractor, Loader, Transformer.

    *How to understand which one you need:*

    1. If you need to get data (**extract**) from **external** source, you need extractor
    2. If you need to send data (**load**) to **external** source, you need loader
    3. If you need to interact with data (**transform**) you need transformer
    """
    _available_methods = ('extract', 'transform', 'load')

    # field for store validation schema
    required_fields: dict = {}

    def __and__(self, other: 'Step') -> 'Step':
        """
        Overriding boolean AND operation for merging steps:

        Example:
        ```python
        EUser(pk=1) & EBook(where=('id', 1))
        ```

        In case any of steps throws an exception, nothing happens
        """
        def run(self, store: frozendict) -> frozendict:

            try:
                result_a = self.obj_a.run(store)
                result_b = self.obj_b.run(store)
            except Exception:
                return store

            return store.copy(**dict(obj_a=result_a, obj_b=result_b))

        return Step.factory(run, 'AndStep', obj_a=self, obj_b=other)()

    def __or__(self, other: 'Step') -> 'Step':
        """
        Overriding boolean OR operation for merging steps:

        Example:
        ```python
        EUser(pk=1) | LError()
        ```

        in case first step throws an exception then store goes to the second step
        with information about an exception in the store

        :param other: Step which merge with
        :return: Step which runs both of the steps according to an operator
        """
        def run(self, store: frozendict) -> frozendict:

            try:
                result = self.obj_a.run(store)
            except Exception as e:
                store = store.copy(**{'exception': e})
                result = self.obj_b.run(store)

            return result

        return Step.factory(run, 'OrStep', obj_a=self, obj_b=other)()

    def _parse_dynamic_fields(self) -> None:
        """
        Processes fields in validation config which should be taken from step instance
        """
        dynamic_config = {}
        keys = list(self.required_fields.keys())

        for key in keys:
            if (key.startswith('+{') or key.startswith('{')) and key.endswith('}'):
                variable_name = re.sub(r'\{|\}', '', key)
                dynamic_config.update({getattr(self, variable_name.replace('+', '')): self.required_fields.get(key)})
                del self.required_fields[key]

        self.required_fields = dict(**self.required_fields, **dynamic_config)

    def validate(self, store: frozendict) -> frozendict:
        """
        Validates store according to `Step.required_fields` field

        :param store:
        :return: Store with adapted data
        """
        self._parse_dynamic_fields()

        validator = V.parse(self.required_fields)
        try:
            adapted = validator.validate(store)
        except V.ValidationError as e:
            raise StepValidationException(
                f'Validation for step {self.__class__.__name__} failed with error \n{e.message}'
            )

        return store.copy(**adapted)

    @classmethod
    def factory(cls, run_method: t.Callable, name: str = '', **arguments) -> type:
        """
        Step factory, creates step with `run_method` provided

        :param run_method: Method which will be runned by pipe
        :param name: Name for a step
        :param arguments: Arguments for a step constructor
        :return: New Step
        """
        return type(name, (cls, ), dict(run=run_method, **arguments))

    def run(self, store: frozendict) -> frozendict:
        """
        Method which provide ability to run any step.

        Pipe shouldn't know which exactly step is
        running, that's why we need run method. But developers should be limited in 3 options,
        which presented in `_available_methods`

        You can extend this class and change `_available_methods` field, if you want to customize
        this behavior

        :param store: Current pipe state
        :return: New frozendict object with updated pipe state
        """

        if self.required_fields is not None:
            store = self.validate(store)

        for method in self._available_methods:
            if hasattr(self, method):
                return getattr(self, method)(store)

        raise StepExecutionException(f"You should define one of this methods - {','.join(self._available_methods)}")


class BasePipe:
    """
    Base class for all pipes, implements running logic and inspection of pipe state on every
    step
    """

    # Flag which show, should pipe print its state every step
    __inspection_mode: bool

    def __init__(self, initial: t.Mapping, inspection: bool = False):
        """
        :param initial: Initial store state
        :param inspection: Inspection mode on/off
        """
        self.__inspection_mode = inspection
        self.store = self.before_pipe(frozendict(initial))

    def set_inspection(self, enable: bool = True) -> bool:
        """
        Sets inspection mode

        Examples:

        **Toggle inspection on:**

        ```python
        MyPipe({}).set_inspection()
        ```

        **Toggle inspection off:*

        ```python
        MyPipe({}).set_inspection(False)
        ```
        """
        self.__inspection_mode = enable

        return self.__inspection_mode

    @staticmethod
    def __print_step(step: Step, store: frozendict) -> None:
        """
        Prints passed step and store to the console

        :param step:
        :param store:
        :return: None
        """
        console = Console()

        console.log('Current step is -> ', step.__class__.__name__, f'({step.__module__})')
        console.log(f'{step.__class__.__name__} STORE STATE')
        console.print(store.__dict__, overflow='fold')
        console.log('\n\n')

    def _run_pipe(self, pipe: t.Iterable[Step]) -> t.Union[None, t.Any]:
        """
        Protected method to run subpipe declared in schema (schema can be different depending on
        pipe type)

        :param pipe:
        :return: Pipe result
        """

        for item in pipe:

            if self.__inspection_mode:
                self.__print_step(item, self.store)

            intermediate_store = item.run(self.store)

            if self.interrupt(intermediate_store):
                return self.after_pipe(intermediate_store)

            self.store = intermediate_store

        return self.after_pipe(self.store)

    def before_pipe(self, store: frozendict) -> frozendict:
        """
        Hook for running custom pipe (or anything) before every pipe execution

        :param store:
        :return: Store
        """
        return store

    def after_pipe(self, store: frozendict) -> frozendict:
        """
        Hook for running custom pipe (or anything) after every pipe execution

        :param store:
        :return: Store
        """
        return store

    def interrupt(self, store: frozendict) -> bool:
        """
        Interruption hook which could be overridden, allow all subclassed pipes set one
        condition, which will
        be respected after any step was run. If method returns true, pipe will not be finished
        and will
        return value returned by step immediately (respects after_pipe hook)

        :param store:
        :return:
        """
        return False

    def __str__(self) -> str:
        return self.__class__.__name__


class NamedPipe(BasePipe):
    """
    Simple pipe structure to interact with named pipes.

    Example:

    ```python
    class MyPipe(NamedPipe):
         pipe_schema = {
             'crop_image': (EImage('<path>'), TCrop(width=230, height=140), LSave('<path>'))
         }

    image_path = MyPipe(<initial_store>).run_pipe('crop_image')
    ```
    """
    pipe_schema: t.Dict[str, t.Iterable[Step]]

    def run_pipe(self, name: str):
        pipe_to_run = self.pipe_schema.get(name, ())
        return self._run_pipe(pipe_to_run)
